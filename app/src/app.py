#!/usr/bin/env python3
import os
import base64
import logging
import asyncio
import functools
import csv
import json
from datetime import datetime, timedelta
from aiohttp import web
from aiohttp_session import setup, get_session, new_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
import jinja2
import aiohttp_jinja2
import stripe

import peony

from sqlalchemy import or_

from common import (
    log,
    send_admin_notification,
    delete_user,
    peony_oauth_step1,
    peony_oauth_step3,
    SemiphemeralPeonyClient,
)
from db import (
    connect_db,
    User,
    Tip,
    RecurringTip,
    Tweet,
    Fascist,
    JobDetails,
)

import worker_jobs

import redis
import rq
from rq import Queue
from rq.job import Job as RQJob, Retry as RQRetry
from rq.registry import FailedJobRegistry

print(f"Connecting to redis at: {os.environ.get('REDIS_URL')}")
conn = redis.from_url(os.environ.get("REDIS_URL"))

jobs_q = Queue("jobs", connection=conn)
dm_jobs_high_q = Queue("dm_jobs_high", connection=conn)

jobs_registry = FailedJobRegistry(queue=jobs_q)
dm_jobs_registry = FailedJobRegistry(queue=dm_jobs_high_q)


async def _logged_in_user(session):
    """
    Return the currently logged in user
    """
    if "twitter_id" in session:
        # Get the user
        user = await User.query.where(
            User.twitter_id == session["twitter_id"]
        ).gino.first()
        if not user:
            del session["twitter_id"]
            return None

        # Are we the administrator impersonating another user?
        if (
            user.twitter_screen_name == os.environ.get("ADMIN_USERNAME")
            and "impersonating_twitter_id" in session
        ):
            await log(
                None,
                f"Admin impersonating user with id {session['impersonating_twitter_id']}",
            )
            impersonating_user = await User.query.where(
                User.twitter_id == session["impersonating_twitter_id"]
            ).gino.first()
            return impersonating_user

        return user

    return None


async def _api_validate(expected_fields, json_data):
    for field in expected_fields:
        if field not in json_data:
            raise web.HTTPBadRequest(text=f"Missing field: {field}")

        invalid_type = False
        if type(expected_fields[field]) == list:
            if type(json_data[field]) not in expected_fields[field]:
                invald_type = True
        else:
            if type(json_data[field]) != expected_fields[field]:
                invalid_type = True
        if invalid_type:
            raise web.HTTPBadRequest(
                text=f"Invalid type: {field} should be {expected_fields[field]}, not {type(json_data[field])}"
            )


async def _api_validate_dms_authenticated(user):
    if (
        user.twitter_dms_access_token != ""
        and user.twitter_dms_access_token_secret != ""
    ):
        # Check if user is authenticated with DMs twitter app
        async with SemiphemeralPeonyClient(user, dms=True) as dms_client:
            try:
                twitter_user = await dms_client.user
                return True
            except Exception as e:
                await log(
                    None,
                    f"DM permissions for @{user.twitter_screen_name} failed to validate: {e}",
                )

    return False


def authentication_required_401(func):
    async def wrapper(request):
        session = await get_session(request)
        if "twitter_id" not in session:
            raise web.HTTPUnauthorized(text="Authentication required")
        user = await User.query.where(
            User.twitter_id == session["twitter_id"]
        ).gino.first()
        if not user:
            raise web.HTTPUnauthorized(text="Authentication required")
        return await func(request)

    return wrapper


def authentication_required_302(func):
    async def wrapper(request):
        session = await get_session(request)
        if "twitter_id" not in session:
            raise web.HTTPFound(location="/")
        user = await User.query.where(
            User.twitter_id == session["twitter_id"]
        ).gino.first()
        if not user:
            raise web.HTTPFound(location="/")
        return await func(request)

    return wrapper


def admin_required(func):
    async def wrapper(request):
        session = await get_session(request)
        user = await User.query.where(
            User.twitter_id == session["twitter_id"]
        ).gino.first()
        if not user or user.twitter_screen_name != os.environ.get("ADMIN_USERNAME"):
            raise web.HTTPNotFound()
        return await func(request)

    return wrapper


async def auth_login(request):
    session = await new_session(request)
    user = await _logged_in_user(session)
    if user:
        # If we're already logged in, redirect
        async with SemiphemeralPeonyClient(user) as client:
            try:
                twitter_user = await client.user
                if twitter_user.id_str == str(User.twitter_id):
                    raise web.HTTPFound("/dashboard")
            except (
                peony.exceptions.InvalidOrExpiredToken,
                peony.exceptions.NotAuthenticated,
            ):
                pass

    # Otherwise, authorize with Twitter
    redirect_url, token = await peony_oauth_step1(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
        "/auth/twitter_callback",
    )
    session["oauth_token"] = token["oauth_token"]
    session["oauth_token_secret"] = token["oauth_token_secret"]
    raise web.HTTPFound(location=redirect_url)


async def auth_logout(request):
    session = await get_session(request)
    del session["twitter_id"]
    if "impersonating_twitter_id" in session:
        del session["impersonating_twitter_id"]
    raise web.HTTPFound(location="/")


async def auth_twitter_callback(request):
    params = request.rel_url.query
    if "denied" in params:
        raise web.HTTPFound(location="/")

    if "oauth_token" not in params or "oauth_verifier" not in params:
        raise web.HTTPUnauthorized(
            text="Error, oauth_token and oauth_verifier are required"
        )

    oauth_token = params["oauth_token"]
    oauth_verifier = params["oauth_verifier"]

    session = await get_session(request)

    if oauth_token != session["oauth_token"]:
        raise web.HTTPUnauthorized(text="Error, invalid oath_token in the session")

    # Authenticate with twitter
    token = await peony_oauth_step3(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
        session["oauth_token"],
        session["oauth_token_secret"],
        oauth_verifier,
    )
    twitter_access_token = token["oauth_token"]
    twitter_access_token_secret = token["oauth_token_secret"]
    twitter_id = token["user_id"]
    twitter_screen_name = token["screen_name"]

    # Save values in the session
    session["twitter_id"] = str(twitter_id)

    # Does this user already exist?
    user = await User.query.where(User.twitter_id == str(twitter_id)).gino.first()
    if user is None:
        # Create a new user
        user = await User.create(
            twitter_id=str(twitter_id),
            twitter_screen_name=twitter_screen_name,
            twitter_access_token=twitter_access_token,
            twitter_access_token_secret=twitter_access_token_secret,
            paused=True,
            blocked=False,
        )

        # Create a new fetch job
        job_details = await JobDetails.create(
            job_type="fetch",
            user_id=user.id,
        )
        redis_job = jobs_q.enqueue(
            worker_jobs.fetch,
            job_details.id,
            job_timeout="24h",
            retry=RQRetry(max=3, interval=[60, 120, 240]),
        )
        await job_details.update(redis_id=redis_job.id).apply()
    else:
        # Make sure to update the user's twitter access token and secret
        await log(None, f"Authenticating user @{user.twitter_screen_name}")
        await user.update(
            twitter_access_token=twitter_access_token,
            twitter_access_token_secret=twitter_access_token_secret,
        ).apply()

    # Redirect to app
    raise web.HTTPFound(location="/dashboard")


async def auth_twitter_dms_callback(request):
    params = request.rel_url.query
    # If denied, I guess just redirect to homepage?
    if "denied" in params:
        raise web.HTTPFound(location="/")

    if "oauth_token" not in params or "oauth_verifier" not in params:
        raise web.HTTPUnauthorized(
            text="Error, oauth_token and oauth_verifier are required"
        )

    oauth_token = params["oauth_token"]
    oauth_verifier = params["oauth_verifier"]

    session = await get_session(request)

    if oauth_token != session["dms_oauth_token"]:
        raise web.HTTPUnauthorized(text="Error, invalid dms_oauth_token in the session")

    # Authenticate with twitter
    token = await peony_oauth_step3(
        os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_DM_CONSUMER_KEY"),
        session["dms_oauth_token"],
        session["dms_oauth_token_secret"],
        oauth_verifier,
    )
    twitter_access_token = token["oauth_token"]
    twitter_access_token_secret = token["oauth_token_secret"]
    twitter_id = token["user_id"]

    # Does this user already exist?
    user = await User.query.where(User.twitter_id == str(twitter_id)).gino.first()
    if user is None:
        # Uh, that's weird, there really should already be a user... so just ignore in that case
        await log(None, f"Authenticating DMs: user is None, this should never happen")
    else:
        # Update the user's DM twitter access token and secret
        await log(None, f"Authenticating DMs for user @{user.twitter_screen_name}")
        await user.update(
            twitter_dms_access_token=twitter_access_token,
            twitter_dms_access_token_secret=twitter_access_token_secret,
        ).apply()

    # Redirect to settings page again
    raise web.HTTPFound(location="/settings")


async def stripe_callback(request):
    message = None
    data = await request.json()

    # TODO: verify webhook signatures
    # webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET_KEY")

    # Charge succeeded
    if data["type"] == "charge.succeeded":
        await log(None, "stripe_callback: charge.succeeded")
        amount_dollars = data["data"]["object"]["amount"] / 100

        tip = await Tip.query.where(
            Tip.stripe_payment_intent == data["data"]["object"]["payment_intent"]
        ).gino.first()
        if tip:
            # Update tip in database
            print("stripe_callback: updating tip in database")
            timestamp = datetime.utcfromtimestamp(data["data"]["object"]["created"])
            await tip.update(
                stripe_charge_id=data["data"]["object"]["id"],
                receipt_url=data["data"]["object"]["receipt_url"],
                paid=data["data"]["object"]["paid"],
                refunded=data["data"]["object"]["refunded"],
                amount=data["data"]["object"]["amount"],
                timestamp=timestamp,
            ).apply()

            user = await User.query.where(User.id == tip.user_id).gino.first()
            if user:
                message = f"https://twitter.com/{user.twitter_screen_name} tipped ${amount_dollars} with stripe"
            else:
                message = f"invalid user (id={tip.user_id}) tipped ${amount_dollars} with stripe"
        else:
            # This was probably a recurring tip
            pass

    # Recurring session has completed
    elif data["type"] == "checkout.session.completed":
        await log(None, "stripe_callback: checkout.session.completed")
        amount_dollars = data["data"]["object"]["amount_total"] / 100
        recurring_tip = await RecurringTip.query.where(
            RecurringTip.stripe_checkout_session_id == data["data"]["object"]["id"]
        ).gino.first()
        if recurring_tip:
            await log(None, "stripe_callback: updating recurring tip in database")
            await recurring_tip.update(
                stripe_customer_id=data["data"]["object"]["customer"],
                stripe_subscription_id=data["data"]["object"]["subscription"],
                amount=data["data"]["object"]["amount_total"],
                status="active",
            ).apply()

            user = await User.query.where(User.id == recurring_tip.user_id).gino.first()
            if user:
                message = f"https://twitter.com/{user.twitter_screen_name} starting ${amount_dollars}/month tips with stripe"
            else:
                message = f"invalid user (id={tip.user_id}) starting ${amount_dollars}/month tips with stripe"
        else:
            await log(None, "stripe_callback: cannot find RecurringTip")

    # Recurring tip paid
    elif data["type"] == "invoice.paid":
        await log(None, "stripe_callback: invoice.paid")
        amount_dollars = data["data"]["object"]["amount_paid"] / 100
        recurring_tip = await RecurringTip.query.where(
            RecurringTip.stripe_customer_id == data["data"]["object"]["customer"]
        ).gino.first()
        if recurring_tip:
            user = await User.query.where(User.id == recurring_tip.user_id).gino.first()
            if user:
                timestamp = datetime.utcfromtimestamp(data["data"]["object"]["created"])
                await Tip.create(
                    user_id=user.id,
                    payment_processor="stripe",
                    stripe_charge_id=data["data"]["object"]["charge"],
                    receipt_url=data["data"]["object"]["hosted_invoice_url"],
                    paid=data["data"]["object"]["paid"],
                    refunded=False,
                    amount=data["data"]["object"]["amount_paid"],
                    timestamp=timestamp,
                    recurring_tip_id=recurring_tip.id,
                )
                message = f"https://twitter.com/{user.twitter_screen_name} tipped ${amount_dollars} (monthly) with stripe"
            else:
                message = f"invalid user (id={tip.user_id}) tipped ${amount_dollars} (monthy) with stripe"
        else:
            # If there's no recurring tip, this was a one-time tip session
            pass

    # Recurring tip payment failed
    elif data["type"] == "invoice.payment_failed":
        await log(None, "stripe_callback: invoice.payment_failed")
        await log(None, json.dumps(data, indent=2))
        message = "A recurring tip payment failed, look at docker logs and implement invoice.payment_failed"

    # Refund a charge
    elif data["type"] == "charge.refunded":
        await log(None, "stripe_callback: charge.refunded")
        charge_id = data["data"]["object"]["id"]
        tip = await Tip.query.where(Tip.stripe_charge_id == charge_id).gino.first()
        if tip:
            await tip.update(refunded=True).apply()

    # All other callbacks
    else:
        await log(None, f"stripe_callback: {data['type']} (not implemented)")

    # Send notification to the admin
    if message:
        await log(None, f"stripe_callback: {message}")
        await send_admin_notification(message)

    return web.HTTPOk()


@authentication_required_401
async def api_get_user(request):
    """
    Respond with information about the logged in user
    """
    session = await get_session(request)

    # Get the actual logged in user
    user = await User.query.where(User.twitter_id == session["twitter_id"]).gino.first()

    # Are we the administrator impersonating another user?
    if (
        user.twitter_screen_name == os.environ.get("ADMIN_USERNAME")
        and "impersonating_twitter_id" in session
    ):
        # Load the API using the admin user
        async with SemiphemeralPeonyClient(user) as client:
            # Load the impersonated user
            user = await _logged_in_user(session)
            twitter_user = await client.api.users.lookup.get(
                screen_name=user.twitter_screen_name
            )
    else:
        # Just a normal user
        async with SemiphemeralPeonyClient(user) as client:
            twitter_user = await client.api.users.lookup.get(
                screen_name=user.twitter_screen_name
            )

    twitter_user = twitter_user[0]

    return web.json_response(
        {
            "user_screen_name": user.twitter_screen_name,
            "user_profile_url": twitter_user.profile_image_url_https,
            "last_fetch": user.last_fetch,
        }
    )


@authentication_required_401
async def api_get_settings(request):
    """
    Respond with the logged in user's settings
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    has_fetched = user.since_id != None
    is_dm_app_authenticated = await _api_validate_dms_authenticated(user)

    return web.json_response(
        {
            "has_fetched": has_fetched,
            "delete_tweets": user.delete_tweets,
            "tweets_days_threshold": user.tweets_days_threshold,
            "tweets_enable_retweet_threshold": user.tweets_enable_retweet_threshold,
            "tweets_retweet_threshold": user.tweets_retweet_threshold,
            "tweets_enable_like_threshold": user.tweets_enable_like_threshold,
            "tweets_like_threshold": user.tweets_like_threshold,
            "tweets_threads_threshold": user.tweets_threads_threshold,
            "retweets_likes": user.retweets_likes,
            "retweets_likes_delete_retweets": user.retweets_likes_delete_retweets,
            "retweets_likes_retweets_threshold": user.retweets_likes_retweets_threshold,
            "retweets_likes_delete_likes": user.retweets_likes_delete_likes,
            "retweets_likes_likes_threshold": user.retweets_likes_likes_threshold,
            "direct_messages": user.direct_messages,
            "direct_messages_threshold": user.direct_messages_threshold,
            "is_dm_app_authenticated": is_dm_app_authenticated,
        }
    )


@authentication_required_401
async def api_post_settings(request):
    """
    Update the settings for the currently-logged in user
    """
    session = await get_session(request)
    user = await _logged_in_user(session)
    data = await request.json()

    # Validate
    await _api_validate({"action": str}, data)
    if data["action"] != "save" and data["action"] != "authenticate_dms":
        raise web.HTTPBadRequest(text="action must be 'save' or 'authenticate_dms'")

    await log(
        None,
        f"api_post_settings: user=@{user.twitter_screen_name}, action={data['action']}",
    )

    if data["action"] == "save":
        # Validate some more
        await _api_validate(
            {
                "action": str,
                "delete_tweets": bool,
                "tweets_days_threshold": int,
                "tweets_enable_retweet_threshold": bool,
                "tweets_retweet_threshold": int,
                "tweets_enable_like_threshold": bool,
                "tweets_like_threshold": int,
                "tweets_threads_threshold": bool,
                "retweets_likes": bool,
                "retweets_likes_delete_retweets": bool,
                "retweets_likes_retweets_threshold": int,
                "retweets_likes_delete_likes": bool,
                "retweets_likes_likes_threshold": int,
                "direct_messages": bool,
                "direct_messages_threshold": int,
                "download_all_tweets": bool,
            },
            data,
        )

        # Update settings in the database
        direct_messages_threshold = int(data["direct_messages_threshold"])
        if direct_messages_threshold > 29:
            direct_messages_threshold = 29

        await user.update(
            delete_tweets=data["delete_tweets"],
            tweets_days_threshold=data["tweets_days_threshold"],
            tweets_enable_retweet_threshold=data["tweets_enable_retweet_threshold"],
            tweets_retweet_threshold=data["tweets_retweet_threshold"],
            tweets_enable_like_threshold=data["tweets_enable_like_threshold"],
            tweets_like_threshold=data["tweets_like_threshold"],
            tweets_threads_threshold=data["tweets_threads_threshold"],
            retweets_likes=data["retweets_likes"],
            retweets_likes_delete_retweets=data["retweets_likes_delete_retweets"],
            retweets_likes_retweets_threshold=data["retweets_likes_retweets_threshold"],
            retweets_likes_delete_likes=data["retweets_likes_delete_likes"],
            retweets_likes_likes_threshold=data["retweets_likes_likes_threshold"],
            direct_messages=data["direct_messages"],
            direct_messages_threshold=direct_messages_threshold,
        ).apply()

        # Does the user want to force downloading all tweets next time?
        if data["download_all_tweets"]:
            await user.update(since_id=None).apply()

        return web.json_response(True)

    if data["action"] == "authenticate_dms":
        # Authorize with Twitter
        redirect_url, token = await peony_oauth_step1(
            os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
            os.environ.get("TWITTER_DM_CONSUMER_KEY"),
            "/auth/twitter_dms_callback",
        )
        session["dms_oauth_token"] = token["oauth_token"]
        session["dms_oauth_token_secret"] = token["oauth_token_secret"]
        return web.json_response({"error": False, "redirect_url": redirect_url})


@authentication_required_401
async def api_post_settings_delete_account(request):
    """
    Delete the account and all data associated with the user, and log out
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    await log(
        None, f"api_post_settings_delete_account: user=@{user.twitter_screen_name}"
    )

    # Log the user out
    session = await get_session(request)
    del session["twitter_id"]

    # Delete user and all associated data
    await delete_user(user)

    return web.json_response(True)


@authentication_required_302
async def api_get_export_download(request):
    """
    Download CSV export of tweets
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    # Create the CSV
    os.makedirs(
        os.path.join("/tmp", "export", str(user.twitter_screen_name)), exist_ok=True
    )
    csv_filename = os.path.join(
        "/tmp", "export", str(user.twitter_screen_name), "export.csv"
    )
    with open(csv_filename, "w") as f:
        fieldnames = [
            "Date",  # created_at
            "Username",  # twitter_user_screen_name
            "Tweet ID",  # status_id
            "Text",  # text
            "Replying to Username",  # in_reply_to_screen_name
            "Replying to Tweet ID",  # in_reply_to_status_id
            "Retweets",  # retweet_count
            "Likes",  # favorite_count
            "Retweeted",  # is_retweet
            "Liked",  # favorited
            "URL",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, dialect="unix")
        writer.writeheader()

        tweets = (
            await Tweet.query.where(Tweet.user_id == user.id)
            .where(Tweet.twitter_user_id == user.twitter_id)
            .where(Tweet.is_deleted == False)
            .where(Tweet.is_unliked == False)
            .order_by(Tweet.created_at.desc())
            .gino.all()
        )
        for tweet in tweets:
            url = f"https://twitter.com/{user.twitter_screen_name}/status/{tweet.status_id}"

            # Write the row
            writer.writerow(
                {
                    "Date": tweet.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "Username": tweet.twitter_user_screen_name,
                    "Tweet ID": str(tweet.status_id),
                    "Text": tweet.text,
                    "Replying to Username": tweet.in_reply_to_screen_name,
                    "Replying to Tweet ID": str(tweet.in_reply_to_status_id),
                    "Retweets": str(tweet.retweet_count),
                    "Likes": str(tweet.favorite_count),
                    "Retweeted": str(tweet.is_retweet),
                    "Liked": str(tweet.favorited),
                    "URL": url,
                }
            )

    download_filename = f"semiphemeral-export-{user.twitter_screen_name}-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return web.FileResponse(
        csv_filename,
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


@authentication_required_401
async def api_get_tip(request):
    """
    Respond with all information necessary for Stripe tips
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    tips = (
        await Tip.query.where(Tip.user_id == user.id)
        .where(Tip.paid == True)
        .order_by(Tip.timestamp.desc())
        .gino.all()
    )

    recurring_tips = (
        await RecurringTip.query.where(RecurringTip.user_id == user.id)
        .where(RecurringTip.status == "active")
        .order_by(RecurringTip.timestamp.desc())
        .gino.all()
    )

    def tip_to_client(tip):
        return {
            "timestamp": tip.timestamp.timestamp(),
            "amount": tip.amount,
            "paid": tip.paid,
            "refunded": tip.refunded,
            "receipt_url": tip.receipt_url,
        }

    def recurring_tip_to_client(recurring_tip):
        return {
            "id": recurring_tip.id,
            "payment_processor": recurring_tip.payment_processor,
            "amount": recurring_tip.amount,
        }

    return web.json_response(
        {
            "stripe_publishable_key": os.environ.get("STRIPE_PUBLISHABLE_KEY"),
            "tips": [tip_to_client(tip) for tip in tips],
            "recurring_tips": [
                recurring_tip_to_client(recurring_tip)
                for recurring_tip in recurring_tips
            ],
        }
    )


@authentication_required_302
async def api_post_tip(request):
    """
    Submit a tip, to redirect to payment processor
    """
    session = await get_session(request)
    user = await _logged_in_user(session)
    data = await request.json()

    # Validate
    await _api_validate(
        {
            "amount": str,
            "other_amount": [str, float],
            "type": str,
        },
        data,
    )
    if (
        data["amount"] != "100"
        and data["amount"] != "200"
        and data["amount"] != "500"
        and data["amount"] != "1337"
        and data["amount"] != "2000"
        and data["amount"] != "10000"
        and data["amount"] != "other"
    ):
        return web.json_response({"error": True, "error_message": "Invalid amount"})
    if data["type"] != "one-time" and data["type"] != "monthly":
        return web.json_response({"error": True, "error_message": "Invalid type"})
    if data["amount"] == "other":
        if float(data["other_amount"]) < 0:
            return web.json_response(
                {
                    "error": True,
                    "error_message": "Mess with the best, die like the rest",
                }
            )
        elif float(data["other_amount"]) < 1:
            return web.json_response(
                {"error": True, "error_message": "You must tip at least $1"}
            )

    # How much is being tipped?
    if data["amount"] == "other":
        amount = int(float(data["other_amount"]) * 100)
    else:
        amount = int(data["amount"])

    # Is it recurring?
    recurring = data["type"] == "monthly"

    try:
        # Create a checkout session
        loop = asyncio.get_running_loop()
        domain = os.environ.get("DOMAIN")
        if recurring:
            # Make sure this Price object exists
            price_id = None

            prices = await loop.run_in_executor(
                None,
                functools.partial(
                    stripe.Price.list, limit=100, recurring={"interval": "month"}
                ),
            )
            for price in prices["data"]:
                if price["unit_amount"] == amount:
                    price_id = price["id"]
                    break

            if not price_id:
                price = await loop.run_in_executor(
                    None,
                    functools.partial(
                        stripe.Price.create,
                        unit_amount=amount,
                        currency="usd",
                        recurring={"interval": "month"},
                        product_data={
                            "name": "Monthly Tip",
                            "statement_descriptor": "SEMIPHEMERAL TIP",
                        },
                    ),
                )
                price_id = price["id"]

            checkout_session = await loop.run_in_executor(
                None,
                functools.partial(
                    stripe.checkout.Session.create,
                    payment_method_types=["card"],
                    success_url=f"https://{domain}/thanks",
                    cancel_url=f"https://{domain}/cancel-tip",
                    mode="subscription",
                    line_items=[
                        {"price": price_id, "quantity": 1},
                    ],
                ),
            )

            await RecurringTip.create(
                user_id=user.id,
                payment_processor="stripe",
                stripe_checkout_session_id=checkout_session.id,
                status="pending",
                timestamp=datetime.now(),
            )
        else:
            checkout_session = await loop.run_in_executor(
                None,
                functools.partial(
                    stripe.checkout.Session.create,
                    submit_type="donate",
                    payment_method_types=["card"],
                    success_url=f"https://{domain}/thanks",
                    cancel_url=f"https://{domain}/cancel-tip",
                    mode="payment",
                    line_items=[
                        {
                            "price_data": {
                                "currency": "usd",
                                "unit_amount": amount,
                                "product_data": {
                                    "name": "Semiphemeral tip",
                                    "images": [
                                        f"https://semiphemeral.com/static/img/logo.png"
                                    ],
                                },
                            },
                            "quantity": 1,
                        },
                    ],
                ),
            )

            await Tip.create(
                user_id=user.id,
                payment_processor="stripe",
                stripe_payment_intent=checkout_session.payment_intent,
                paid=False,
                timestamp=datetime.now(),
            )

        return web.json_response({"error": False, "id": checkout_session.id})

    except Exception as e:
        return web.json_response(
            {"error": True, "error_message": f"Something went wrong: {e}"}
        )


@authentication_required_302
async def api_post_tip_cancel_recurring(request):
    """
    Cancel a recurring tip
    """
    session = await get_session(request)
    user = await _logged_in_user(session)
    data = await request.json()

    # Validate
    await _api_validate(
        {
            "recurring_tip_id": int,
        },
        data,
    )

    # Get the recurring tip, and validate
    recurring_tip = await RecurringTip.query.where(
        RecurringTip.id == data["recurring_tip_id"]
    ).gino.first()
    if not recurring_tip:
        return web.json_response(
            {"error": True, "error_message": f"Cannot find recurring tip"}
        )
    if recurring_tip.user_id != user.id:
        return web.json_response(
            {"error": True, "error_message": f"What do you think you're trying to do?"}
        )

    # Cancel the recurring tip
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            stripe.Subscription.delete, sid=recurring_tip.stripe_subscription_id
        ),
    )
    await recurring_tip.update(status="canceled").apply()
    return web.json_response({"error": False})


@authentication_required_401
async def api_get_tip_recent(request):
    """
    Respond with the receipt_url for the most recent tip from this user
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    tip = (
        await Tip.query.where(Tip.id == user.id)
        .where(Tip.paid == True)
        .where(Tip.refunded == False)
        .order_by(Tip.timestamp.desc())
        .gino.first()
    )

    if tip:
        receipt_url = tip.receipt_url
    else:
        receipt_url = None

    return web.json_response({"receipt_url": receipt_url})


@authentication_required_401
async def api_get_dashboard(request):
    """
    Respond with the current user's list of active and pending jobs
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    pending_jobs = (
        await JobDetails.query.where(JobDetails.user_id == user.id)
        .where(JobDetails.status == "pending")
        .order_by(JobDetails.scheduled_timestamp)
        .gino.all()
    )

    active_jobs = (
        await JobDetails.query.where(JobDetails.user_id == user.id)
        .where(JobDetails.status == "active")
        .order_by(JobDetails.started_timestamp)
        .gino.all()
    )

    finished_jobs = (
        await JobDetails.query.where(JobDetails.user_id == user.id)
        .where(JobDetails.status == "finished")
        .order_by(JobDetails.finished_timestamp.desc())
        .gino.all()
    )

    def to_client(jobs):
        jobs_json = []
        for job in jobs:
            if job.scheduled_timestamp:
                scheduled_timestamp = job.scheduled_timestamp.timestamp()
            else:
                scheduled_timestamp = None
            if job.started_timestamp:
                started_timestamp = job.started_timestamp.timestamp()
            else:
                started_timestamp = None
            if job.finished_timestamp:
                finished_timestamp = job.finished_timestamp.timestamp()
            else:
                finished_timestamp = None

            jobs_json.append(
                {
                    "id": job.id,
                    "job_type": job.job_type,
                    "data": job.data,
                    "status": job.status,
                    "scheduled_timestamp": scheduled_timestamp,
                    "started_timestamp": started_timestamp,
                    "finished_timestamp": finished_timestamp,
                }
            )
        return jobs_json

    fascist_tweets = []
    if user.blocked:
        # Get fascist tweets that this user has liked
        six_months_ago = datetime.now() - timedelta(days=180)
        fascist_tweets = (
            await Tweet.query.where(Tweet.user_id == user.id)
            .where(Tweet.favorited == True)
            .where(Tweet.is_fascist == True)
            .where(Tweet.created_at > six_months_ago)
            .order_by(Tweet.created_at.desc())
            .gino.all()
        )
        fascist_tweets = [
            {
                "status_id": tweet.status_id,
                "permalink": f"https://twitter.com/{tweet.twitter_user_screen_name}/status/{tweet.status_id}",
            }
            for tweet in fascist_tweets
        ]

    return web.json_response(
        {
            "pending_jobs": to_client(pending_jobs),
            "active_jobs": to_client(active_jobs),
            "finished_jobs": to_client(finished_jobs),
            "setting_paused": user.paused,
            "setting_blocked": user.blocked,
            "setting_delete_tweets": user.delete_tweets,
            "setting_retweets_likes": user.retweets_likes,
            "setting_direct_messages": user.direct_messages,
            "fascist_tweets": fascist_tweets,
        }
    )


@authentication_required_401
async def api_post_dashboard(request):
    """
    Start or pause semiphemeral, or fetch.

    If action is start, the user paused, and there are no pending or active jobs:
      unpause and create a delete job
    If action is pause and the user is not paused:
      cancel any active or pending jobs and pause
    If action is fetch, the user is paused, and there are no pending or active jobs:
      create a fetch job
    If action is unblock and the user is blocked and hasn't liked too many fascist tweets:
      create an unblock job
    If action is reactivate and the user is blocked:
      see if the user is still blocked, and if not set blocked=False and create a fetch job
    """
    session = await get_session(request)
    user = await _logged_in_user(session)
    data = await request.json()

    # Validate
    await _api_validate({"action": str}, data)
    if (
        data["action"] != "start"
        and data["action"] != "pause"
        and data["action"] != "fetch"
        and data["action"] != "unblock"
        and data["action"] != "reactivate"
    ):
        raise web.HTTPBadRequest(
            text="action must be 'start', 'pause', 'fetch', or 'reactivate'"
        )

    await log(
        None,
        f"api_post_dashboard: user=@{user.twitter_screen_name}, action={data['action']}",
    )

    if data["action"] == "unblock":
        if not user.blocked:
            raise web.HTTPBadRequest(text="Can only 'unblock' if the user is blocked")

        # Are we still blocked?
        async with SemiphemeralPeonyClient(user) as client:
            friendship = await client.api.friendships.show.get(
                source_screen_name=user.twitter_screen_name,
                target_screen_name="semiphemeral",
            )

        if friendship["relationship"]["source"]["blocked_by"]:
            # Still blocked by semiphemeral. Should we unblock?

            # Count fascist tweets
            fascist_tweets = (
                await Tweet.query.where(Tweet.user_id == user.id)
                .where(Tweet.favorited == True)
                .where(Tweet.is_fascist == True)
                .order_by(Tweet.created_at.desc())
                .gino.all()
            )
            if len(fascist_tweets) > 15:
                return web.json_response(
                    {
                        "message": "You've liked too many fascist tweets to be allowed to automatically unblock yourself"
                    }
                )
            else:
                # They liked few enough fascist tweets, so create an unblock job
                job_details = await JobDetails.create(
                    job_type="unblock",
                    data=json.dumps({"twitter_username": user.twitter_screen_name}),
                )
                redis_job = jobs_q.enqueue(
                    worker_jobs.unblock,
                    job_details.id,
                    retry=RQRetry(max=3, interval=[60, 120, 240]),
                )
                await job_details.update(redis_id=redis_job.id).apply()
                return web.json_response(
                    {"message": "You should be unblocked in the next few minutes"}
                )
        else:
            # The user is already unblocked, so update them in the db
            await user.update(blocked=False, since_id=None).apply()

            return web.json_response({"message": "You are already unblocked"})

    if data["action"] == "reactivate":
        if not user.blocked:
            raise web.HTTPBadRequest(
                text="Can only 'reactivate' if the user is blocked"
            )

        # Are we still blocked?
        async with SemiphemeralPeonyClient(user) as client:
            friendship = await client.api.friendships.show.get(
                source_screen_name=user.twitter_screen_name,
                target_screen_name="semiphemeral",
            )

        if friendship["relationship"]["source"]["blocked_by"]:
            return web.json_response({"unblocked": False})
        else:
            # Delete the user's likes so we can start over and check them all
            await Tweet.delete.where(Tweet.user_id == user.id).where(
                Tweet.favorited == True
            ).gino.status()

            # User has been unblocked
            await user.update(blocked=False, since_id=None).apply()

            # Create a new fetch job
            job_details = await JobDetails.create(
                job_type="fetch",
                user_id=user.id,
            )
            redis_job = jobs_q.enqueue(
                worker_jobs.fetch,
                job_details.id,
                job_timeout="24h",
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
            await job_details.update(redis_id=redis_job.id).apply()

            return web.json_response({"unblocked": True})

    else:
        # Get pending and active jobs
        pending_jobs = (
            await JobDetails.query.where(JobDetails.user_id == user.id)
            .where(JobDetails.status == "pending")
            .gino.all()
        )
        active_jobs = (
            await JobDetails.query.where(JobDetails.user_id == user.id)
            .where(JobDetails.status == "active")
            .gino.all()
        )
        jobs = pending_jobs + active_jobs

        if data["action"] == "start":
            if not user.paused:
                raise web.HTTPBadRequest(
                    text="Cannot 'start' unless semiphemeral is paused"
                )
            if len(jobs) > 0:
                raise web.HTTPBadRequest(
                    text="Cannot 'start' when there are pending or active jobs"
                )

            # Unpause
            await user.update(paused=False).apply()

            # Create a new delete job
            job_details = await JobDetails.create(
                job_type="delete",
                user_id=user.id,
            )
            redis_job = jobs_q.enqueue(
                worker_jobs.delete,
                job_details.id,
                job_timeout="24h",
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
            await job_details.update(redis_id=redis_job.id).apply()

        elif data["action"] == "pause":
            if user.paused:
                raise web.HTTPBadRequest(
                    text="Cannot 'pause' when semiphemeral is already paused"
                )

            # Cancel jobs
            for job in jobs:
                try:
                    redis_job = RQJob.fetch(job.redis_id, connection=conn)
                    redis_job.cancel()
                    redis_job.delete()
                except rq.exceptions.NoSuchJobError:
                    pass
                await job.update(status="canceled").apply()

            # Pause
            await user.update(paused=True).apply()

        elif data["action"] == "fetch":
            if not user.paused:
                raise web.HTTPBadRequest(
                    text="Cannot 'fetch' unless semiphemeral is paused"
                )

            if len(jobs) > 0:
                raise web.HTTPBadRequest(
                    text="Cannot 'fetch' when there are pending or active jobs"
                )

            # Create a new fetch job
            job_details = await JobDetails.create(
                job_type="fetch",
                user_id=user.id,
            )
            redis_job = jobs_q.enqueue(
                worker_jobs.fetch,
                job_details.id,
                job_timeout="24h",
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
            await job_details.update(redis_id=redis_job.id).apply()

        return web.json_response(True)


@authentication_required_401
async def api_get_tweets(request):
    """
    Respond with the current user's list of tweets
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    tweets_for_client = []
    for tweet in (
        await Tweet.query.where(Tweet.user_id == user.id)
        .where(Tweet.twitter_user_id == user.twitter_id)
        .where(Tweet.is_deleted == False)
        .where(Tweet.is_retweet == False)
        .order_by(Tweet.created_at.desc())
        .gino.all()
    ):
        created_at = tweet.created_at.timestamp()
        is_reply = tweet.in_reply_to_status_id is not None
        tweets_for_client.append(
            {
                "created_at": created_at,
                "status_id": str(
                    tweet.status_id
                ),  # Typecast it to a string, to avoid javascript issues
                "text": tweet.text,
                "is_reply": is_reply,
                "retweet_count": tweet.retweet_count,
                "like_count": tweet.favorite_count,
                "exclude": tweet.exclude_from_delete,
            }
        )

    return web.json_response({"tweets": tweets_for_client})


@authentication_required_401
async def api_post_tweets(request):
    """
    Toggle "exclude for deletion" on a tweet
    """
    session = await get_session(request)
    user = await _logged_in_user(session)
    data = await request.json()

    # Validate
    await _api_validate({"status_id": str, "exclude": bool}, data)
    tweet = (
        await Tweet.query.where(Tweet.user_id == user.id)
        .where(Tweet.twitter_user_id == user.twitter_id)
        .where(Tweet.status_id == data["status_id"])
        .gino.first()
    )
    if not tweet:
        raise web.HTTPBadRequest(text="Invalid status_id")

    # Update exclude from delete
    await tweet.update(exclude_from_delete=data["exclude"]).apply()

    return web.json_response(True)


@authentication_required_401
async def api_get_dms(request):
    """
    Get information about deleting DMs
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    is_dm_app_authenticated = await _api_validate_dms_authenticated(user)

    job = (
        await JobDetails.query.where(JobDetails.user_id == user.id)
        .where(
            or_(
                JobDetails.job_type == "delete_dms",
                JobDetails.job_type == "delete_dm_groups",
            )
        )
        .where(or_(JobDetails.status == "pending", JobDetails.status == "active"))
        .gino.first()
    )
    is_dm_job_ongoing = job is not None

    return web.json_response(
        {
            "direct_messages": user.direct_messages,
            "is_dm_app_authenticated": is_dm_app_authenticated,
            "is_dm_job_ongoing": is_dm_job_ongoing,
        }
    )


@authentication_required_401
async def api_post_dms(request):
    """
    Upload a direct-message-headers.js file to bulk delete old DMs
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    if not await _api_validate_dms_authenticated(user):
        return web.json_response(
            {
                "error": True,
                "error_message": "You are not authenticated to the Semiphemeral DMs Twitter app",
            }
        )
    if not user.direct_messages:
        return web.json_response(
            {
                "error": True,
                "error_message": "You have not enabled deleting direct messages in your settings",
            }
        )

    # Validate
    post = await request.post()
    dms_file = post.get("file")
    if not dms_file:
        return web.json_response(
            {
                "error": True,
                "error_message": "Uploading file failed",
            }
        )

    # Detect if this is direct-message-headers.js or direct-message-group-headers.js
    expected_dm_start = b"window.YTD.direct_message_headers.part0 = "
    expected_dm_group_start = b"window.YTD.direct_message_group_headers.part0 = "

    content = dms_file.file.read()
    if content.startswith(expected_dm_start):
        dm_type = "dms"
        json_string = content[len(expected_dm_start) :]
    elif content.startswith(expected_dm_group_start):
        dm_type = "groups"
        json_string = content[len(expected_dm_group_start) :]
    else:
        return web.json_response(
            {
                "error": True,
                "error_message": "This does not appear to be a direct-message-headers.js or direct-message-group-headers.js file",
            }
        )

    try:
        conversations = json.loads(json_string)
    except:
        return web.json_response(
            {
                "error": True,
                "error_message": "Failed parsing JSON object",
            }
        )

    if type(conversations) != list:
        return web.json_response(
            {
                "error": True,
                "error_message": "JSON object expected to be a list",
            }
        )

    for obj in conversations:
        if type(obj) != dict:
            return web.json_response(
                {
                    "error": True,
                    "error_message": "JSON object expected to be a list of dicts",
                }
            )
        if "dmConversation" not in obj:
            return web.json_response(
                {
                    "error": True,
                    "error_message": "JSON object expected to be a list of dicts that contain 'dmConversation' fields",
                }
            )
        dm_conversation = obj["dmConversation"]
        if "messages" not in dm_conversation:
            return web.json_response(
                {
                    "error": True,
                    "error_message": "JSON object expected to be a list of dicts that contain 'dmConversations' fields that contain 'messages' fields",
                }
            )

    # Save to disk
    if dm_type == "dms":
        job_type = "delete_dms"
        filename = os.path.join("/var/bulk_dms", f"dms-{user.id}.json")
    elif dm_type == "groups":
        job_type = "delete_dm_groups"
        filename = os.path.join("/var/bulk_dms", f"groups-{user.id}.json")
    with open(filename, "w") as f:
        f.write(json.dumps(conversations, indent=2))

    # Create a new delete_dms job
    job_details = await JobDetails.create(
        job_type="delete_dms",
        user_id=user.id,
    )
    if dm_type == "dms":
        redis_job = jobs_q.enqueue(
            worker_jobs.delete_dms,
            job_details.id,
            job_timeout="24h",
            retry=RQRetry(max=3, interval=[60, 120, 240]),
        )
        await job_details.update(redis_id=redis_job.id).apply()
    elif dm_type == "groups":
        redis_job = jobs_q.enqueue(
            worker_jobs.delete_dm_groups,
            job_details.id,
            job_timeout="24h",
            retry=RQRetry(max=3, interval=[60, 120, 240]),
        )
        await job_details.update(redis_id=redis_job.id).apply()

    return web.json_response({"error": False})


@aiohttp_jinja2.template("index.jinja2")
async def index(request):
    session = await get_session(request)
    user = await _logged_in_user(session)
    logged_in = user is not None
    return {"logged_in": logged_in}


@aiohttp_jinja2.template("privacy.jinja2")
async def privacy(request):
    return {}


@authentication_required_302
async def app_main(request):
    with open("frontend/dist/index.html") as f:
        body = f.read()
    
    return web.Response(text=body, content_type="text/html")


@admin_required
async def app_admin(request):
    with open("admin-frontend/dist/index.html") as f:
        body = f.read()
    
    return web.Response(text=body, content_type="text/html")


@admin_required
async def app_admin_redirect(request):
    raise web.HTTPFound(location="/admin/jobs")


@admin_required
async def admin_api_get_jobs(request):
    jobs = (
        await JobDetails.query.where(
            or_(JobDetails.status == "active", JobDetails.status == "pending")
        )
        .order_by(JobDetails.id)
        .gino.all()
    )

    async def to_client(job):
        if job.scheduled_timestamp:
            scheduled_timestamp = job.scheduled_timestamp.timestamp()
        else:
            scheduled_timestamp = None
        if job.started_timestamp:
            started_timestamp = job.started_timestamp.timestamp()
        else:
            started_timestamp = None

        user = await User.query.where(User.id == job.user_id).gino.first()
        if user:
            twitter_username = user.twitter_screen_name
            twitter_link = f"https://twitter.com/{user.twitter_screen_name}"
        else:
            twitter_username = None
            twitter_link = None

        try:
            redis_job = RQJob.fetch(job.redis_id, connection=conn)
            redis_status = redis_job.get_status(refresh=True)
        except rq.exceptions.NoSuchJobError:
            redis_status = "N/A"

        return {
            "id": job.id,
            "user_id": job.user_id,
            "twitter_username": twitter_username,
            "twitter_link": twitter_link,
            "job_type": job.job_type,
            "data": json.loads(job.data),
            "status": job.status,
            "scheduled_timestamp": scheduled_timestamp,
            "started_timestamp": started_timestamp,
            "redis_status": redis_status,
        }

    started_jobs = []
    queued_jobs = []
    scheduled_jobs = []
    other_jobs = []

    for job in jobs:
        job_json = await to_client(job)
        if job_json["redis_status"] == "started":
            started_jobs.append(job_json)
        elif job_json["redis_status"] == "queued":
            queued_jobs.append(job_json)
        elif job_json["redis_status"] == "scheduled":
            scheduled_jobs.append(job_json)
        else:
            other_jobs.append(job_json)

    return web.json_response(
        {
            "started_jobs": started_jobs,
            "queued_jobs": queued_jobs,
            "scheduled_jobs": scheduled_jobs,
            "other_jobs": other_jobs,
        }
    )


@admin_required
async def admin_api_get_users(request):
    users = await User.query.order_by(User.twitter_screen_name).gino.all()
    active_users = []
    paused_users = []
    blocked_users = []

    for user in users:
        if user.blocked:
            blocked_users.append(user)
        else:
            if user.paused:
                paused_users.append(user)
            else:
                active_users.append(user)

    def to_client(users):
        users_json = []
        for user in users:
            users_json.append(
                {
                    "id": user.id,
                    "twitter_id": user.twitter_id,
                    "twitter_screen_name": user.twitter_screen_name,
                    "blocked": user.blocked,
                }
            )
        return users_json

    session = await get_session(request)

    impersonating_twitter_id = None
    impersonating_twitter_username = None

    if "impersonating_twitter_id" in session:
        impersonating_user = await User.query.where(
            User.twitter_id == session["impersonating_twitter_id"]
        ).gino.first()
        if impersonating_user:
            impersonating_twitter_id = session["impersonating_twitter_id"]
            impersonating_twitter_username = impersonating_user.twitter_screen_name

    return web.json_response(
        {
            "impersonating_twitter_id": impersonating_twitter_id,
            "impersonating_twitter_username": impersonating_twitter_username,
            "active_users": to_client(active_users),
            "paused_users": to_client(paused_users),
            "blocked_users": to_client(blocked_users),
        }
    )


@admin_required
async def admin_api_get_user(request):
    user_id = int(request.match_info["user_id"])
    user = await User.query.where(User.id == user_id).gino.first()
    if not user:
        return web.json_response(False)

    # Get fascist tweets that this user has liked
    fascist_tweets = (
        await Tweet.query.where(Tweet.user_id == user_id)
        .where(Tweet.favorited == True)
        .where(Tweet.is_fascist == True)
        .order_by(Tweet.created_at.desc())
        .gino.all()
    )
    fascist_tweet_urls = [
        f"https://twitter.com/{tweet.twitter_user_screen_name}/status/{tweet.status_id}"
        for tweet in fascist_tweets
    ]

    return web.json_response(
        {
            "twitter_username": user.twitter_screen_name,
            "paused": user.paused,
            "blocked": user.blocked,
            "fascist_tweet_urls": fascist_tweet_urls,
        }
    )


@admin_required
async def admin_api_post_user_impersonate(request):
    session = await get_session(request)
    data = await request.json()

    # Validate
    await _api_validate({"twitter_id": str}, data)
    if data["twitter_id"] == "0":
        del session["impersonating_twitter_id"]
    else:
        impersonating_user = await User.query.where(
            User.twitter_id == data["twitter_id"]
        ).gino.first()
        if impersonating_user:
            session["impersonating_twitter_id"] = data["twitter_id"]

    return web.json_response(True)


@admin_required
async def admin_api_get_fascists(request):
    fascists = await Fascist.query.order_by(Fascist.username).gino.all()

    def to_client(fascists):
        fascists_json = []
        for fascist in fascists:
            fascists_json.append(
                {
                    "username": fascist.username,
                    "comment": fascist.comment,
                }
            )
        return fascists_json

    return web.json_response({"fascists": to_client(fascists)})


@admin_required
async def admin_api_post_fascists(request):
    data = await request.json()

    # Validate
    await _api_validate({"action": str}, data)
    if data["action"] != "create" and data["action"] != "delete":
        raise web.HTTPBadRequest(text="action must be 'create' or 'delete'")

    if data["action"] == "create":
        await _api_validate({"action": str, "username": str, "comment": str}, data)

        # If a fascist with this username already exists, just update the comment
        fascist = await Fascist.query.where(
            Fascist.username == data["username"]
        ).gino.first()
        if fascist:
            await fascist.update(comment=data["comment"]).apply()
            return web.json_response(True)

        # Create the fascist
        fascist = await Fascist.create(
            username=data["username"], comment=data["comment"]
        )

        # Mark all the tweets from this user as is_fascist=True
        await Tweet.update.values(is_fascist=True).where(
            Tweet.twitter_user_screen_name.ilike(data["username"])
        ).gino.status()

        # Make sure the facist is blocked
        job_details = await JobDetails.create(
            job_type="block", data=json.dumps({"twitter_username": data["username"]})
        )
        redis_job = jobs_q.enqueue(
            worker_jobs.block,
            job_details.id,
            retry=RQRetry(max=3, interval=[60, 120, 240]),
        )
        await job_details.update(redis_id=redis_job.id).apply()

        return web.json_response(True)

    elif data["action"] == "delete":
        await _api_validate({"action": str, "username": str}, data)

        # Delete the fascist
        fascist = await Fascist.query.where(
            Fascist.username == data["username"]
        ).gino.first()
        if fascist:
            await fascist.delete()

        # Mark all the tweets from this user as is_fascist=False
        await Tweet.update.values(is_fascist=False).where(
            Tweet.twitter_user_screen_name == data["username"]
        ).gino.status()

        return web.json_response(True)


@admin_required
async def admin_api_get_tips(request):
    users = {}
    tips = await Tip.query.order_by(Tip.timestamp.desc()).gino.all()

    for tip in tips:
        if tip.user_id not in users:
            user = await User.query.where(User.id == tip.user_id).gino.first()
            if user:
                users[tip.user_id] = {
                    "twitter_username": user.twitter_screen_name,
                    "twitter_link": f"https://twitter.com/{user.twitter_screen_name}",
                }
            else:
                users[tip.user_id] = {"twitter_username": "", "twitter_link": ""}

    def to_client(tips):
        tips_json = []
        for tip in tips:
            tips_json.append(
                {
                    "twitter_username": users[tip.user_id]["twitter_username"],
                    "twitter_link": users[tip.user_id]["twitter_link"],
                    "timestamp": tip.timestamp.timestamp(),
                    "amount": tip.amount,
                    "paid": tip.paid,
                    "refunded": tip.refunded,
                    "receipt_url": tip.receipt_url,
                }
            )
        return tips_json

    return web.json_response({"tips": to_client(tips)})


async def maintenance_refresh_logging(request=None):
    """
    Refreshes logging. This needs to get run after rotating logs, to re-open the
    web.log file
    """
    logging.basicConfig(filename="/var/web/web.log", level=logging.INFO, force=True)

    if request:
        return web.json_response(True)


async def main():
    print("Connecting to the database")
    await connect_db()

    await send_admin_notification(
        f"Semiphemeral container started ({os.environ.get('DEPLOY_ENVIRONMENT')})"
    )

    # If staging, start by pausing all users and cancel all pending jobs
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        await log(
            None, "Staging environment, so pausing all users and canceling all jobs"
        )
        await User.update.values(paused=True).gino.status()

        await JobDetails.update.values(status="pending").where(
            JobDetails.status == "active"
        ).gino.status()

        pending_jobs = await JobDetails.query.where(
            JobDetails.status == "pending"
        ).gino.all()
        for job in pending_jobs:
            try:
                redis_job = RQJob.fetch(job.redis_id, connection=conn)
                redis_job.cancel()
                redis_job.delete()
            except rq.exceptions.NoSuchJobError:
                pass

        await JobDetails.update.values(status="canceled").where(
            JobDetails.status == "pending"
        ).gino.status()

    # Start over all active jobs
    await log(None, "Make 'active' jobs 'pending', and start them")
    active_jobs = await JobDetails.query.where(JobDetails.status == "active").gino.all()
    for job_details in active_jobs:
        if job_details.job_type == "fetch":
            redis_job = jobs_q.enqueue(
                worker_jobs.fetch,
                job_details.id,
                job_timeout="24h",
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
        elif job_details.job_type == "delete":
            redis_job = jobs_q.enqueue(
                worker_jobs.delete,
                job_details.id,
                job_timeout="24h",
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
        elif job_details.job_type == "delete_dms":
            redis_job = jobs_q.enqueue(
                worker_jobs.delete_dms,
                job_details.id,
                job_timeout="24h",
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
        elif job_details.job_type == "delete_dm_groups":
            redis_job = jobs_q.enqueue(
                worker_jobs.delete_dm_groups,
                job_details.id,
                job_timeout="24h",
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
        elif job_details.job_type == "block":
            redis_job = jobs_q.enqueue(
                worker_jobs.block,
                job_details.id,
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
        elif job_details.job_type == "unblock":
            redis_job = jobs_q.enqueue(
                worker_jobs.unblock,
                job_details.id,
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
        elif job_details.job_type == "dm":
            redis_job = dm_jobs_high_q.enqueue(
                worker_jobs.dm,
                job_details.id,
                retry=RQRetry(max=3, interval=[60, 120, 240]),
            )
        await job_details.update(status="pending", redis_id=redis_job.id).apply()

    # Init stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

    # Create the web app
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("templates"))
    await maintenance_refresh_logging()

    # Secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = os.environ.get("COOKIE_FERNET_KEY")
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))

    # Define routes
    app.add_routes(
        [
            # Static files
            web.static("/static", "static"),
            web.static("/assets", "frontend/dist/assets"),
            web.static("/admin-assets", "admin-frontend/dist/admin-assets"),
            # Authentication
            web.get("/auth/login", auth_login),
            web.get("/auth/logout", auth_logout),
            web.get("/auth/twitter_callback", auth_twitter_callback),
            web.get("/auth/twitter_dms_callback", auth_twitter_dms_callback),
            # Stripe
            web.post("/stripe/callback", stripe_callback),
            # API
            web.get("/api/user", api_get_user),
            web.get("/api/settings", api_get_settings),
            web.post("/api/settings", api_post_settings),
            web.post("/api/settings/delete_account", api_post_settings_delete_account),
            web.get("/api/tip", api_get_tip),
            web.post("/api/tip", api_post_tip),
            web.post("/api/tip/cancel_recurring", api_post_tip_cancel_recurring),
            web.get("/api/tip/recent", api_get_tip_recent),
            web.get("/api/dashboard", api_get_dashboard),
            web.post("/api/dashboard", api_post_dashboard),
            web.get("/api/tweets", api_get_tweets),
            web.post("/api/tweets", api_post_tweets),
            web.get("/api/dms", api_get_dms),
            web.post("/api/dms", api_post_dms),
            # Web
            web.get("/", index),
            web.get("/privacy", privacy),
            web.get("/dashboard", app_main),
            web.get("/tweets", app_main),
            web.get("/export", app_main),
            web.get("/export/download", api_get_export_download),
            web.get("/dms", app_main),
            web.get("/settings", app_main),
            web.get("/tip", app_main),
            web.get("/thanks", app_main),
            web.get("/cancel-tip", app_main),
            web.get("/faq", app_main),
            # Admin
            web.get("/admin", app_admin_redirect),
            web.get("/admin/jobs", app_admin),
            web.get("/admin/users", app_admin),
            web.get("/admin/fascists", app_admin),
            web.get("/admin/tips", app_admin),
            # Admin API
            web.get("/admin_api/jobs", admin_api_get_jobs),
            web.get("/admin_api/users", admin_api_get_users),
            web.get("/admin_api/users/{user_id}", admin_api_get_user),
            web.post("/admin_api/users/impersonate", admin_api_post_user_impersonate),
            web.get("/admin_api/fascists", admin_api_get_fascists),
            web.post("/admin_api/fascists", admin_api_post_fascists),
            web.get("/admin_api/tips", admin_api_get_tips),
            # Maintenance
            web.get(
                f"/{os.environ.get('MAINTENANCE_SECRET')}/refresh_logging",
                maintenance_refresh_logging,
            ),
        ]
    )

    runner = web.AppRunner(app)
    await runner.setup()
    server = web.TCPSite(runner, port=8080)
    await server.start()
    print("Server started at http://127.0.0.1:8080")

    # Loop forever logging redis job exceptions
    with open("/var/web/exceptions.log", "a") as f:
        logged_job_ids = []
        while True:
            exceptions_logged = 0
            for job_id in jobs_registry.get_job_ids():
                if job_id not in logged_job_ids:
                    job = RQJob.fetch(job_id, connection=conn)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"job_id is {job_id}, timestamp is {now}\n")
                    f.write(job.exc_info)
                    f.write("===\n")
                    f.flush()
                    logged_job_ids.append(job_id)
                    exceptions_logged += 1
            if exceptions_logged > 0:
                print(f"Logged {exceptions_logged} exceptions")

            await asyncio.sleep(20)


if __name__ == "__main__":
    asyncio.run(main())
