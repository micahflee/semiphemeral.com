#!/usr/bin/env python3
import os
import csv
import json
from datetime import datetime, timedelta
import stripe
import tweepy

from sqlalchemy import select, update, delete, or_
from sqlalchemy.sql import text
from db import (
    User,
    Tip,
    RecurringTip,
    Tweet,
    Like,
    Fascist,
    JobDetails,
    engine as db_engine,
    session as db_session,
)

from common import (
    log,
    send_admin_notification,
    delete_user,
    create_tweepy_api_1_1,
    tweepy_api_v1_1,
    tweepy_dms_api_v1_1,
    tweepy_semiphemeral_api_1_1,
    conn,
    jobs_q,
    dm_jobs_high_q,
    add_job,
    add_dm_job,
    conn as redis_conn,
)

from flask import (
    Flask,
    send_from_directory,
    session,
    redirect,
    request,
    jsonify,
    render_template,
)
from flask_session import Session
from functools import wraps

import worker_jobs

import rq
from rq.job import Job as RQJob

# Init stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

# Start flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

SESSION_TYPE = "redis"
SESSION_REDIS = redis_conn
app.config.from_object(__name__)
Session(app)


# Helpers


def _logged_in_user():
    """
    Return the currently logged in user
    """
    if session.get("twitter_id"):
        user = db_session.scalar(
            select(User).where(User.twitter_id == session.get("twitter_id"))
        )
        if not user:
            session["twitter_id"] = None
            return None

        # Are we the administrator impersonating another user?
        if user.twitter_screen_name == os.environ.get("ADMIN_USERNAME") and session.get(
            "impersonating_twitter_id"
        ):
            impersonating_user = db_session.scalar(
                select(User).where(
                    User.twitter_id == session.get("impersonating_twitter_id")
                )
            )

            return impersonating_user

        return user

    return None


def _api_validate(expected_fields, json_data):
    for field in expected_fields:
        if field not in json_data:
            return {"valid": False, "message": f"Missing field: {field}"}

        invalid_type = False
        if type(expected_fields[field]) == list:
            if type(json_data[field]) not in expected_fields[field]:
                invalid_type = True
        else:
            if type(json_data[field]) != expected_fields[field]:
                invalid_type = True
        if invalid_type:
            return {
                "valid": False,
                "message": f"Invalid type: {field} should be {expected_fields[field]}, not {type(json_data[field])}",
            }

    return {"valid": True}


def _api_validate_dms_authenticated(user):
    # Check if user is authenticated with DMs twitter app
    dms_api = tweepy_dms_api_v1_1(user)
    try:
        dms_api.verify_credentials()
        return True
    except Exception as e:
        return False


# Decorators


def authentication_required_401(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        current_user = _logged_in_user()
        if not current_user:
            return "Authentication required", 401

        return f(current_user, *args, **kwargs)

    return decorator


def authentication_required_302(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        current_user = _logged_in_user()
        if not current_user:
            return redirect("/", 302)

        return f(current_user, *args, **kwargs)

    return decorator


def admin_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        current_user = _logged_in_user()
        if session.get("impersonating_twitter_id"):
            user = db_session.scalar(
                select(User).where(User.twitter_id == session.get("twitter_id"))
            )
            if not user or user.twitter_screen_name != os.environ.get("ADMIN_USERNAME"):
                return redirect("/", 302)
        else:
            if not current_user or current_user.twitter_screen_name != os.environ.get(
                "ADMIN_USERNAME"
            ):
                return redirect("/", 302)

        return f(current_user, *args, **kwargs)

    return decorator


# Static files


@app.route("/images/<path:filename>")
def static_images(filename):
    return send_from_directory("images", filename)


@app.route("/assets/<path:filename>")
def static_assets(filename):
    return send_from_directory(
        f"frontend/dist-{os.environ.get('DEPLOY_ENVIRONMENT')}/assets", filename
    )


@app.route("/admin-assets/<path:filename>")
def static_admin_assets(filename):
    return send_from_directory(
        f"admin-frontend/dist-{os.environ.get('DEPLOY_ENVIRONMENT')}/admin-assets",
        filename,
    )


# Authentication routes


@app.route("/auth/login")
def auth_login():
    user = _logged_in_user()
    if user:
        # If we're already logged in, redirect
        api = tweepy_api_v1_1(user)
        try:
            response = api.verify_credentials()
            if response.id_str == User.twitter_id:
                return redirect("/dashboard", code=302)
        except Exception as e:
            pass

    # Otherwise, authorize with Twitter
    oauth1_user_handler = tweepy.OAuth1UserHandler(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
        callback=f"https://{os.environ.get('DOMAIN')}/auth/twitter_callback",
    )
    redirect_url = oauth1_user_handler.get_authorization_url()
    session["oath_request_token"] = oauth1_user_handler.request_token["oauth_token"]
    session["oath_request_secret"] = oauth1_user_handler.request_token[
        "oauth_token_secret"
    ]
    return redirect(redirect_url, code=302)


@app.route("/auth/logout")
def auth_logout():
    session["twitter_id"] = None
    session["impersonating_twitter_id"] = None
    return redirect("/", code=302)


@app.route("/auth/twitter_callback")
def auth_twitter_callback():
    if "denied" in request.args:
        return redirect("/", code=302)

    if "oauth_token" not in request.args or "oauth_verifier" not in request.args:
        return "Error, oauth_token and oauth_verifier are required", 401

    oauth_token = request.args["oauth_token"]
    oauth_verifier = request.args["oauth_verifier"]

    if oauth_token != session.get("oath_request_token"):
        return "Error, invalid oath_token in the session", 401

    oauth1_user_handler = tweepy.OAuth1UserHandler(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
        callback=f"https://{os.environ.get('DOMAIN')}/auth/twitter_callback",
    )
    oauth1_user_handler.request_token = {
        "oauth_token": session["oath_request_token"],
        "oauth_token_secret": session["oath_request_secret"],
    }
    access_token, access_token_secret = oauth1_user_handler.get_access_token(
        oauth_verifier
    )

    # Authenticate with twitter
    api = create_tweepy_api_1_1(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
        access_token,
        access_token_secret,
    )
    try:
        response = api.verify_credentials()
    except Exception as e:
        return f"Error: {e}", 401

    twitter_id = response.id_str
    username = response.screen_name

    # Save values in the session
    session["twitter_id"] = twitter_id

    # Does this user already exist?
    user = db_session.scalar(select(User).where(User.twitter_id == twitter_id))
    if user is None:
        # Create a new user
        user = User(
            twitter_id=twitter_id,
            twitter_screen_name=username,
            twitter_access_token=access_token,
            twitter_access_token_secret=access_token_secret,
            paused=True,
            blocked=False,
        )
        db_session.add(user)
        db_session.commit()

        # Create a new fetch job
        add_job("fetch", user.id, worker_jobs.funcs)
    else:
        # Make sure to update the user's twitter access token and secret
        log(None, f"Authenticating user @{user.twitter_screen_name}")
        user.twitter_access_token = access_token
        user.twitter_access_token_secret = access_token_secret
        db_session.add(user)
        db_session.commit()

    # Redirect to app
    return redirect("/dashboard", code=302)


@app.route("/auth/twitter_dms_callback")
def auth_twitter_dms_callback():
    if "denied" in request.args:
        return redirect("/", code=302)

    if "oauth_token" not in request.args or "oauth_verifier" not in request.args:
        return "Error, oauth_token and oauth_verifier are required", 401

    oauth_token = request.args["oauth_token"]
    oauth_verifier = request.args["oauth_verifier"]

    if oauth_token != session.get("dms_oath_request_token"):
        return "Error, invalid oath_token in the session", 401

    oauth1_user_handler = tweepy.OAuth1UserHandler(
        os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_DM_CONSUMER_KEY"),
        callback=f"https://{os.environ.get('DOMAIN')}/auth/twitter_dms_callback",
    )
    oauth1_user_handler.request_token = {
        "oauth_token": session["dms_oath_request_token"],
        "oauth_token_secret": session["dms_oath_request_secret"],
    }
    access_token, access_token_secret = oauth1_user_handler.get_access_token(
        oauth_verifier
    )

    # Authenticate with twitter
    api = create_tweepy_api_1_1(
        os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_DM_CONSUMER_KEY"),
        access_token,
        access_token_secret,
    )
    try:
        response = api.verify_credentials()
    except Exception as e:
        return f"Error: {e}", 401

    twitter_id = response.id_str

    # Does this user already exist?
    user = db_session.scalar(select(User).where(User.twitter_id == twitter_id))
    if user is None:
        # Uh, that's weird, there really should already be a user... so just ignore in that case
        log(None, f"Authenticating DMs: user is None, this should never happen")
    else:
        # Update the user's DM twitter access token and secret
        log(None, f"Authenticating DMs for user @{user.twitter_screen_name}")
        user.twitter_dms_access_token = access_token
        user.twitter_dms_access_token_secret = access_token_secret
        db_session.add(user)
        db_session.commit()

    # Redirect to settings page again
    return redirect("/settings", code=302)


# Stripe callback


@app.route("/stripe/callback", methods=["POST"])
def stripe_callback():
    try:
        stripe_payload = json.loads(request.data)
    except Exception as e:
        log(None, f"Error parsing Stripe payload: {e}")
        return jsonify(success=False)

    message = None

    # TODO: verify webhook signatures
    # webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET_KEY")

    # Charge succeeded
    if stripe_payload["type"] == "charge.succeeded":
        log(None, "stripe_callback: charge.succeeded")
        amount_dollars = stripe_payload["data"]["object"]["amount"] / 100

        tip = db_session.scalar(
            select(Tip).where(
                Tip.stripe_payment_intent
                == stripe_payload["data"]["object"]["payment_intent"]
            )
        )
        if tip:
            # Update tip in database
            print("stripe_callback: updating tip in database")
            timestamp = datetime.utcfromtimestamp(
                stripe_payload["data"]["object"]["created"]
            )

            tip.stripe_charge_id = stripe_payload["data"]["object"]["id"]
            tip.receipt_url = stripe_payload["data"]["object"]["receipt_url"]
            tip.paid = stripe_payload["data"]["object"]["paid"]
            tip.refunded = stripe_payload["data"]["object"]["refunded"]
            tip.amount = stripe_payload["data"]["object"]["amount"]
            tip.timestamp = timestamp
            db_session.add(tip)
            db_session.commit()

            user = db_session.scalar(select(User).where(User.id == tip.user_id))
            if user:
                message = f"https://twitter.com/{user.twitter_screen_name} tipped ${amount_dollars} with stripe"
            else:
                message = f"invalid user (id={tip.user_id}) tipped ${amount_dollars} with stripe"
        else:
            # This was probably a recurring tip
            pass

    # Recurring session has completed
    elif stripe_payload["type"] == "checkout.session.completed":
        log(None, "stripe_callback: checkout.session.completed")
        amount_dollars = stripe_payload["data"]["object"]["amount_total"] / 100
        recurring_tip = db_session.scalar(
            select(RecurringTip).where(
                RecurringTip.stripe_checkout_session_id
                == stripe_payload["data"]["object"]["id"]
            )
        )
        if recurring_tip:
            log(None, "stripe_callback: updating recurring tip in database")

            recurring_tip.stripe_customer_id = stripe_payload["data"]["object"][
                "customer"
            ]
            recurring_tip.stripe_subscription_id = stripe_payload["data"]["object"][
                "subscription"
            ]
            recurring_tip.amount = stripe_payload["data"]["object"]["amount_total"]
            recurring_tip.status = "active"
            db_session.add(recurring_tip)
            db_session.commit()

            user = db_session.scalar(
                select(User).where(User.id == recurring_tip.user_id)
            )
            if user:
                message = f"https://twitter.com/{user.twitter_screen_name} starting ${amount_dollars}/month tips with stripe"
            else:
                message = f"invalid user (id={tip.user_id}) starting ${amount_dollars}/month tips with stripe"
        else:
            log(None, "stripe_callback: cannot find RecurringTip")

    # Recurring tip paid
    elif stripe_payload["type"] == "invoice.paid":
        log(None, "stripe_callback: invoice.paid")
        amount_dollars = stripe_payload["data"]["object"]["amount_paid"] / 100
        recurring_tip = db_session.scalar(
            select(RecurringTip).where(
                RecurringTip.stripe_customer_id
                == stripe_payload["data"]["object"]["customer"]
            )
        )
        if recurring_tip:
            user = db_session.scalar(
                select(User).where(User.id == recurring_tip.user_id)
            )
            if user:
                timestamp = datetime.utcfromtimestamp(
                    stripe_payload["data"]["object"]["created"]
                )
                tip = Tip(
                    user_id=user.id,
                    payment_processor="stripe",
                    stripe_charge_id=stripe_payload["data"]["object"]["charge"],
                    receipt_url=stripe_payload["data"]["object"]["hosted_invoice_url"],
                    paid=stripe_payload["data"]["object"]["paid"],
                    refunded=False,
                    amount=stripe_payload["data"]["object"]["amount_paid"],
                    timestamp=timestamp,
                    recurring_tip_id=recurring_tip.id,
                )
                db_session.add(tip)
                db_session.commit()
                message = f"https://twitter.com/{user.twitter_screen_name} tipped ${amount_dollars} (monthly) with stripe"
            else:
                message = f"invalid user (id={tip.user_id}) tipped ${amount_dollars} (monthy) with stripe"
        else:
            # If there's no recurring tip, this was a one-time tip session
            pass

    # Recurring tip payment failed
    elif stripe_payload["type"] == "invoice.payment_failed":
        log(None, "stripe_callback: invoice.payment_failed")
        log(None, json.dumps(stripe_payload, indent=2))
        message = "A recurring tip payment failed, look at docker logs and implement invoice.payment_failed"

    # Refund a charge
    elif stripe_payload["type"] == "charge.refunded":
        log(None, "stripe_callback: charge.refunded")
        charge_id = stripe_payload["data"]["object"]["id"]
        tip = db_session.scalar(select(Tip).where(Tip.stripe_charge_id == charge_id))
        if tip:
            tip.refunded = True
            db_session.add(tip)
            db_session.commit()

    # All other callbacks
    else:
        log(None, f"stripe_callback: {stripe_payload['type']} (not implemented)")

    # Send notification to the admin
    if message:
        log(None, f"stripe_callback: {message}")
        send_admin_notification(message)

    return jsonify(success=True)


# Public routes


@app.route("/")
def web_index():
    current_user = _logged_in_user()
    logged_in = current_user is not None
    return render_template("index.html", logged_in=logged_in)


@app.route("/privacy")
def web_privacy():
    return render_template("privacy.html")


@app.route("/dashboard")
@app.route("/tweets")
@app.route("/export")
@app.route("/dms")
@app.route("/settings")
@app.route("/tip")
@app.route("/thanks")
@app.route("/cancel-tip")
@app.route("/faq")
@authentication_required_302
def web_main(current_user):
    with open(f"frontend/dist-{os.environ.get('DEPLOY_ENVIRONMENT')}/index.html") as f:
        body = f.read()

    return body


# Admin routes


@app.route("/admin")
@app.route("/admin/jobs")
@app.route("/admin/users")
@app.route("/admin/fascists")
@app.route("/admin/tips")
@admin_required
def admin_main(current_user):
    with open(
        f"admin-frontend/dist-{os.environ.get('DEPLOY_ENVIRONMENT')}/index.html"
    ) as f:
        body = f.read()

    return body


# API routes


@app.route("/api/user")
@authentication_required_401
def api_user(current_user):
    """
    Respond with information about the logged in user
    """
    can_switch = False

    # Are we the administrator impersonating another user?
    if session.get("impersonating_twitter_id"):
        can_switch = True
        log(
            None,
            f"Admin impersonating user @{current_user.twitter_screen_name}",
        )

    api = tweepy_api_v1_1(current_user)
    try:
        response = api.verify_credentials()
        profile_image_url_https = response.profile_image_url_https
    except:
        profile_image_url_https = "/images/egg.png"

    return jsonify(
        {
            "user_screen_name": current_user.twitter_screen_name,
            "user_profile_url": profile_image_url_https,
            "last_fetch": current_user.last_fetch,
            "can_switch": can_switch,
        }
    )


@app.route("/export/download")
@authentication_required_401
def api_export_download(current_user):
    """
    Download CSV export of tweets
    """
    # Create the CSV
    os.makedirs(
        os.path.join("tmp", "export", str(current_user.twitter_screen_name)),
        exist_ok=True,
    )
    download_filename = f"semiphemeral-export-{current_user.twitter_screen_name}-{datetime.now().strftime('%Y-%m-%d')}.csv"
    csv_filename = os.path.join("tmp", "export", download_filename)
    with open(csv_filename, "w") as f:
        fieldnames = [
            "Tweet ID",  # twitter_id
            "Date",  # created_at
            "Text",  # text
            "Retweets",  # retweet_count
            "Likes",  # retweet_count
            "Is Retweet",  # is_retweet
            "URL",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, dialect="unix")
        writer.writeheader()

        tweets = db_session.scalars(
            select(Tweet)
            .where(Tweet.user_id == current_user.id)
            .where(Tweet.is_deleted == False)
            .order_by(Tweet.created_at.desc())
        ).fetchall()
        for tweet in tweets:
            url = f"https://twitter.com/{current_user.twitter_screen_name}/status/{tweet.twitter_id}"

            # Write the row
            writer.writerow(
                {
                    "Tweet ID": str(tweet.twitter_id),
                    "Date": tweet.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "Text": tweet.text,
                    "Retweets": str(tweet.retweet_count),
                    "Likes": str(tweet.like_count),
                    "Is Retweet": str(tweet.is_retweet),
                    "URL": url,
                }
            )

    return send_from_directory("tmp/export", download_filename, as_attachment=True)


@app.route("/api/settings", methods=["GET", "POST"])
@authentication_required_401
def api_settings(current_user):
    """
    GET: Respond with the logged in user's settings
    POST: Update the settings for the currently-logged in user
    """
    if request.method == "GET":
        has_fetched = current_user.since_id != None
        is_dm_app_authenticated = _api_validate_dms_authenticated(current_user)

        return jsonify(
            {
                "has_fetched": has_fetched,
                "delete_tweets": current_user.delete_tweets,
                "tweets_days_threshold": current_user.tweets_days_threshold,
                "tweets_enable_retweet_threshold": current_user.tweets_enable_retweet_threshold,
                "tweets_retweet_threshold": current_user.tweets_retweet_threshold,
                "tweets_enable_like_threshold": current_user.tweets_enable_like_threshold,
                "tweets_like_threshold": current_user.tweets_like_threshold,
                "tweets_threads_threshold": current_user.tweets_threads_threshold,
                "retweets_likes": current_user.retweets_likes,
                "retweets_likes_delete_retweets": current_user.retweets_likes_delete_retweets,
                "retweets_likes_retweets_threshold": current_user.retweets_likes_retweets_threshold,
                "retweets_likes_delete_likes": current_user.retweets_likes_delete_likes,
                "retweets_likes_likes_threshold": current_user.retweets_likes_likes_threshold,
                "direct_messages": current_user.direct_messages,
                "direct_messages_threshold": current_user.direct_messages_threshold,
                "is_dm_app_authenticated": is_dm_app_authenticated,
            }
        )

    elif request.method == "POST":
        try:
            data = json.loads(request.data)
        except Exception as e:
            log(None, f"Error parsing JSON: {e}")
            return jsonify({"error": True, "error_message": "Error parsing JSON"})

        # Validate
        valid = _api_validate({"action": str}, data)
        if not valid["valid"]:
            return valid["message"], 400
        if data["action"] != "save" and data["action"] != "authenticate_dms":
            return "action must be 'save' or 'authenticate_dms'", 400

        log(
            None,
            f"api_post_settings: user=@{current_user.twitter_screen_name}, action={data['action']}",
        )

        if data["action"] == "save":
            # Validate some more
            valid = _api_validate(
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
            if not valid["valid"]:
                return valid["message"], 400

            # Update settings in the database
            direct_messages_threshold = int(data["direct_messages_threshold"])
            if direct_messages_threshold > 29:
                direct_messages_threshold = 29

            current_user.delete_tweets = data["delete_tweets"]
            current_user.tweets_days_threshold = data["tweets_days_threshold"]
            current_user.tweets_enable_retweet_threshold = data[
                "tweets_enable_retweet_threshold"
            ]
            current_user.tweets_retweet_threshold = data["tweets_retweet_threshold"]
            current_user.tweets_enable_like_threshold = data[
                "tweets_enable_like_threshold"
            ]
            current_user.tweets_like_threshold = data["tweets_like_threshold"]
            current_user.tweets_threads_threshold = data["tweets_threads_threshold"]
            current_user.retweets_likes = data["retweets_likes"]
            current_user.retweets_likes_delete_retweets = data[
                "retweets_likes_delete_retweets"
            ]
            current_user.retweets_likes_retweets_threshold = data[
                "retweets_likes_retweets_threshold"
            ]
            current_user.retweets_likes_delete_likes = data[
                "retweets_likes_delete_likes"
            ]
            current_user.retweets_likes_likes_threshold = data[
                "retweets_likes_likes_threshold"
            ]
            current_user.direct_messages = data["direct_messages"]
            current_user.direct_messages_threshold = direct_messages_threshold

            # Does the user want to force downloading all tweets next time?
            if data["download_all_tweets"]:
                current_user.since_id = None

            db_session.add(current_user)
            db_session.commit()

            return jsonify(True)

        if data["action"] == "authenticate_dms":
            # Authorize with Twitter
            oauth1_user_handler = tweepy.OAuth1UserHandler(
                os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
                os.environ.get("TWITTER_DM_CONSUMER_KEY"),
                callback=f"https://{os.environ.get('DOMAIN')}/auth/twitter_dms_callback",
            )
            redirect_url = oauth1_user_handler.get_authorization_url()
            session["dms_oath_request_token"] = oauth1_user_handler.request_token[
                "oauth_token"
            ]
            session["dms_oath_request_secret"] = oauth1_user_handler.request_token[
                "oauth_token_secret"
            ]
            return jsonify({"error": False, "redirect_url": redirect_url})

    else:
        return "Bad request", 400


@app.route("/api/settings/delete_account", methods=["POST"])
@authentication_required_401
def api_delete_account(current_user):
    """
    Delete the account and all data associated with the user, and log out
    """
    log(None, f"api_delete_account: user=@{current_user.twitter_screen_name}")
    session["twitter_id"] = None
    delete_user(current_user)
    return jsonify(True)


@app.route("/api/tip", methods=["GET", "POST"])
@authentication_required_401
def api_tip(current_user):
    """
    GET: Respond with all information necessary for Stripe tips
    POST: Submit a tip, to redirect to payment processor
    """
    if request.method == "GET":
        tips = db_session.scalars(
            select(Tip)
            .where(Tip.user_id == current_user.id)
            .where(Tip.paid == True)
            .order_by(Tip.timestamp.desc())
        ).fetchall()

        recurring_tips = db_session.scalars(
            select(RecurringTip)
            .where(RecurringTip.user_id == current_user.id)
            .where(RecurringTip.status == "active")
            .order_by(RecurringTip.timestamp.desc())
        ).fetchall()

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

        return jsonify(
            {
                "stripe_publishable_key": os.environ.get("STRIPE_PUBLISHABLE_KEY"),
                "tips": [tip_to_client(tip) for tip in tips],
                "recurring_tips": [
                    recurring_tip_to_client(recurring_tip)
                    for recurring_tip in recurring_tips
                ],
            }
        )

    elif request.method == "POST":
        try:
            data = json.loads(request.data)
        except Exception as e:
            log(None, f"Error parsing JSON: {e}")
            return jsonify({"error": True, "error_message": "Error parsing JSON"})

        # Validate
        valid = _api_validate(
            {
                "amount": str,
                "other_amount": [int, float],
                "type": str,
            },
            data,
        )
        if not valid["valid"]:
            return valid["message"], 400

        if (
            data["amount"] != "100"
            and data["amount"] != "200"
            and data["amount"] != "500"
            and data["amount"] != "1337"
            and data["amount"] != "2000"
            and data["amount"] != "10000"
            and data["amount"] != "other"
        ):
            return jsonify({"error": True, "error_message": "Invalid amount"})
        if data["type"] != "one-time" and data["type"] != "monthly":
            return jsonify({"error": True, "error_message": "Invalid type"})
        if data["amount"] == "other":
            if float(data["other_amount"]) < 0:
                return jsonify(
                    {
                        "error": True,
                        "error_message": "Mess with the best, die like the rest",
                    }
                )
            elif float(data["other_amount"]) < 1:
                return jsonify(
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
            domain = os.environ.get("DOMAIN")
            if recurring:
                # Make sure this Price object exists
                price_id = None

                prices = stripe.Price.list(limit=100, recurring={"interval": "month"})
                for price in prices["data"]:
                    if price["unit_amount"] == amount:
                        price_id = price["id"]
                        break

                if not price_id:
                    price = stripe.Price.create(
                        unit_amount=amount,
                        currency="usd",
                        recurring={"interval": "month"},
                        product_data={
                            "name": "Monthly Tip",
                            "statement_descriptor": "SEMIPHEMERAL TIP",
                        },
                    )
                    price_id = price["id"]

                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    success_url=f"https://{domain}/thanks",
                    cancel_url=f"https://{domain}/cancel-tip",
                    mode="subscription",
                    line_items=[
                        {"price": price_id, "quantity": 1},
                    ],
                )

                recurring_tip = RecurringTip(
                    user_id=current_user.id,
                    payment_processor="stripe",
                    stripe_checkout_session_id=checkout_session.id,
                    status="pending",
                    timestamp=datetime.now(),
                )
                db_session.add(recurring_tip)
                db_session.commit()
            else:
                checkout_session = stripe.checkout.Session.create(
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
                )

                tip = Tip(
                    user_id=current_user.id,
                    payment_processor="stripe",
                    stripe_payment_intent=checkout_session.payment_intent,
                    paid=False,
                    timestamp=datetime.now(),
                )
                db_session.add(tip)
                db_session.commit()

            return jsonify({"error": False, "id": checkout_session.id})

        except Exception as e:
            return jsonify(
                {"error": True, "error_message": f"Something went wrong: {e}"}
            )

    else:
        return "Bad request", 400


@app.route("/api/tip/cancel_recurring", methods=["POST"])
@authentication_required_401
def api_tip_cancel_recurring(current_user):
    """
    Cancel a recurring tip
    """
    try:
        data = json.loads(request.data)
    except Exception as e:
        log(None, f"Error parsing JSON: {e}")
        return jsonify({"error": True, "error_message": "Error parsing JSON"})

    # Validate
    valid = _api_validate(
        {
            "recurring_tip_id": int,
        },
        data,
    )
    if not valid["valid"]:
        return valid["message"], 400

    # Get the recurring tip, and validate
    recurring_tip = db_session.scalar(
        select(RecurringTip).where(RecurringTip.id == data["recurring_tip_id"])
    )
    if not recurring_tip:
        return jsonify({"error": True, "error_message": f"Cannot find recurring tip"})
    if recurring_tip.user_id != current_user.id:
        return jsonify(
            {"error": True, "error_message": f"What do you think you're trying to do?"}
        )

    # Cancel the recurring tip
    stripe.Subscription.delete(sid=recurring_tip.stripe_subscription_id)
    recurring_tip.status = "canceled"
    db_session.add(recurring_tip)
    db_session.commit()
    return jsonify({"error": False})


@app.route("/api/tip/recent")
@authentication_required_401
def api_tip_recent(current_user):
    """
    Respond with the receipt_url for the most recent tip from this user
    """
    tip = db_session.scalar(
        select(Tip)
        .where(Tip.user_id == current_user.id)
        .where(Tip.paid == True)
        .where(Tip.refunded == False)
        .order_by(Tip.timestamp.desc())
    )

    if tip:
        receipt_url = tip.receipt_url
    else:
        receipt_url = None

    return jsonify({"receipt_url": receipt_url})


@app.route("/api/dashboard", methods=["GET", "POST"])
@authentication_required_401
def api_dashboard(current_user):
    """
    GET: Respond with the current user's list of active and pending jobs
    POST: Start or pause semiphemeral, or fetch.
    """
    if request.method == "GET":
        pending_jobs = db_session.scalars(
            select(JobDetails)
            .where(JobDetails.user_id == current_user.id)
            .where(JobDetails.status == "pending")
            .order_by(JobDetails.scheduled_timestamp)
        ).fetchall()

        active_jobs = db_session.scalars(
            select(JobDetails)
            .where(JobDetails.user_id == current_user.id)
            .where(JobDetails.status == "active")
            .order_by(JobDetails.started_timestamp)
        ).fetchall()

        finished_jobs = db_session.scalars(
            select(JobDetails)
            .where(JobDetails.user_id == current_user.id)
            .where(JobDetails.status == "finished")
            .order_by(JobDetails.finished_timestamp.desc())
        ).fetchall()

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

        fascist_likes = []
        fascist_likes_to_client = []
        if current_user.blocked:
            # Get fascist tweets that this user has liked
            six_months_ago = datetime.now() - timedelta(days=180)
            fascist_likes = db_session.scalars(
                select(Like)
                .where(Like.user_id == current_user.id)
                .where(Like.is_fascist == True)
                .where(Like.created_at > six_months_ago)
                .order_by(Like.created_at.desc())
            ).fetchall()

            # use the Semiphemeral API, so we don't need to authenticate with the blocked user's creds
            api = tweepy_semiphemeral_api_1_1()

            for like in fascist_likes:
                response = api.get_status(like.twitter_id)
                try:
                    text = response.text
                except:
                    text = ""
                try:
                    created_at = response.created_at.timestamp()
                except:
                    created_at = 0
                try:
                    name = response.author.name
                except:
                    name = ""
                try:
                    username = response.author.screen_name
                except:
                    username = ""

                if username != "":
                    permalink = (
                        f"https://twitter.com/{username}/status/{like.twitter_id}"
                    )
                else:
                    permalink = (
                        f"https://twitter.com/semiphemeral/status/{like.twitter_id}"
                    )
                fascist_likes_to_client.append(
                    {
                        "twitter_id": like.twitter_id,
                        "name": name,
                        "username": username,
                        "text": text,
                        "created_at": created_at,
                        "permalink": permalink,
                    }
                )

        return jsonify(
            {
                "pending_jobs": to_client(pending_jobs),
                "active_jobs": to_client(active_jobs),
                "finished_jobs": to_client(finished_jobs),
                "setting_paused": current_user.paused,
                "setting_blocked": current_user.blocked,
                "setting_delete_tweets": current_user.delete_tweets,
                "setting_retweets_likes": current_user.retweets_likes,
                "setting_direct_messages": current_user.direct_messages,
                "fascist_likes": fascist_likes_to_client,
            }
        )

    elif request.method == "POST":
        """
        If action is start, the user paused, and there are no pending or active jobs: unpause and create a delete job
        If action is pause and the user is not paused: cancel any active or pending jobs and pause
        If action is fetch, the user is paused, and there are no pending or active jobs: create a fetch job
        If action is unblock and the user is blocked and hasn't liked too many fascist tweets: create an unblock job
        If action is reactivate and the user is blocked: see if the user is still blocked, and if not set blocked=False and create a fetch job
        """
        try:
            data = json.loads(request.data)
        except Exception as e:
            log(None, f"Error parsing JSON: {e}")
            return jsonify({"error": True, "error_message": "Error parsing JSON"})

        # Validate
        valid = _api_validate({"action": str}, data)
        if not valid["valid"]:
            return valid["message"], 400

        if (
            data["action"] != "start"
            and data["action"] != "pause"
            and data["action"] != "fetch"
            and data["action"] != "unblock"
            and data["action"] != "reactivate"
        ):
            return "action must be 'start', 'pause', 'fetch', or 'reactivate'", 400

        log(
            None,
            f"api_post_dashboard: user=@{current_user.twitter_screen_name}, action={data['action']}",
        )

        if data["action"] == "unblock":
            if not current_user.blocked:
                return "Can only 'unblock' if the user is blocked", 400

            # Unblock the user
            semiphemeral_api = tweepy_semiphemeral_api_1_1()
            try:
                semiphemeral_api.destroy_block(user_id=current_user.twitter_id)
            except Exception as e:
                log(
                    None,
                    f"Error unblocking: {e}",
                )

            current_user.blocked = False
            current_user.since_id = None
            db_session.add(current_user)
            db_session.commit()
            return jsonify({"message": "You are unblocked"})

        if data["action"] == "reactivate":
            if not current_user.blocked:
                return "Can only 'reactivate' if the user is blocked", 400

            # Delete the user's likes so we can start over and check them all
            db_session.execute(delete(Like).where(Like.user_id == current_user.id))

            # User has been unblocked
            current_user.blocked = False
            current_user.since_id = None
            db_session.add(current_user)

            db_session.commit()

            # Create a new fetch job
            add_job("fetch", current_user.id, worker_jobs.funcs)

            return jsonify({"unblocked": True})

        else:
            # Get pending and active jobs
            pending_jobs = db_session.scalars(
                select(JobDetails)
                .where(JobDetails.user_id == current_user.id)
                .where(JobDetails.status == "pending")
            ).fetchall()
            active_jobs = db_session.scalars(
                select(JobDetails)
                .where(JobDetails.user_id == current_user.id)
                .where(JobDetails.status == "active")
            ).fetchall()
            jobs = pending_jobs + active_jobs

            if data["action"] == "start":
                if not current_user.paused:
                    return "Cannot 'start' unless semiphemeral is paused", 400
                if len(jobs) > 0:
                    return "Cannot 'start' when there are pending or active jobs", 400

                # Unpause
                current_user.paused = False
                db_session.add(current_user)
                db_session.commit()

                # Create a new delete job
                add_job("delete", current_user.id, worker_jobs.funcs)

            elif data["action"] == "pause":
                if current_user.paused:
                    return "Cannot 'pause' when semiphemeral is already paused", 400

                # Cancel jobs
                for job in jobs:
                    try:
                        redis_job = RQJob.fetch(job.redis_id, connection=conn)
                        redis_job.cancel()
                        redis_job.delete()
                    except rq.exceptions.NoSuchJobError:
                        pass
                    job.status = "canceled"
                    db_session.add(job)
                    db_session.commit()

                # Pause
                current_user.paused = True
                db_session.add(current_user)
                db_session.commit()

            elif data["action"] == "fetch":
                if not current_user.paused:
                    return "Cannot 'fetch' unless semiphemeral is paused"

                if len(jobs) > 0:
                    return "Cannot 'fetch' when there are pending or active jobs", 400

                # Create a new fetch job
                add_job("fetch", current_user.id, worker_jobs.funcs)

            return jsonify(True)

    else:
        return "Bad request", 400


@app.route("/api/tweets", methods=["GET", "POST"])
@authentication_required_401
def api_tweets(current_user):
    """
    GET: Respond with the current user's list of active and pending jobs
    POST: Start or pause semiphemeral, or fetch.
    """
    if request.method == "GET":
        tweets_for_client = []
        tweets = db_session.scalars(
            select(Tweet)
            .where(Tweet.user_id == current_user.id)
            .where(Tweet.is_deleted == False)
            .where(Tweet.is_retweet == False)
            .order_by(Tweet.created_at.desc())
        ).fetchall()
        for tweet in tweets:
            created_at = tweet.created_at.timestamp()
            tweets_for_client.append(
                {
                    "created_at": created_at,
                    "status_id": str(tweet.twitter_id),
                    "text": tweet.text,
                    "is_reply": tweet.is_reply,
                    "retweet_count": tweet.retweet_count,
                    "like_count": tweet.like_count,
                    "exclude": tweet.exclude_from_delete,
                }
            )

        return jsonify({"tweets": tweets_for_client})

    elif request.method == "POST":
        try:
            data = json.loads(request.data)
        except Exception as e:
            log(None, f"Error parsing JSON: {e}")
            return jsonify({"error": True, "error_message": "Error parsing JSON"})

        # Validate
        valid = _api_validate({"status_id": str, "exclude": bool}, data)
        if not valid["valid"]:
            return valid["message"], 400

        tweet = db_session.scalar(
            select(Tweet)
            .where(Tweet.user_id == current_user.id)
            .where(Tweet.twitter_id == data["status_id"])
        )
        if not tweet:
            return "Invalid status_id", 400

        # Update exclude from delete
        tweet.exclude_from_delete = data["exclude"]
        db_session.add(tweet)
        db_session.commit()

        return jsonify(True)

    else:
        return "Bad request", 400


@app.route("/api/dms", methods=["GET", "POST"])
@authentication_required_401
def api_dms(current_user):
    """
    GET: Get information about deleting DMs
    POST: Upload a direct-message-headers.js file to bulk delete old DMs
    """
    if request.method == "GET":
        is_dm_app_authenticated = _api_validate_dms_authenticated(current_user)

        job = db_session.scalar(
            select(JobDetails)
            .where(JobDetails.user_id == current_user.id)
            .where(
                or_(
                    JobDetails.job_type == "delete_dms",
                    JobDetails.job_type == "delete_dm_groups",
                )
            )
            .where(or_(JobDetails.status == "pending", JobDetails.status == "active"))
        )
        is_dm_job_ongoing = job is not None

        return jsonify(
            {
                "direct_messages": current_user.direct_messages,
                "is_dm_app_authenticated": is_dm_app_authenticated,
                "is_dm_job_ongoing": is_dm_job_ongoing,
            }
        )

    elif request.method == "POST":
        if not _api_validate_dms_authenticated(current_user):
            return jsonify(
                {
                    "error": True,
                    "error_message": "You are not authenticated to the Semiphemeral DMs Twitter app",
                }
            )
        if not current_user.direct_messages:
            return jsonify(
                {
                    "error": True,
                    "error_message": "You have not enabled deleting direct messages in your settings",
                }
            )

        # Validate
        dms_file = request.files.get("file")
        if not dms_file or dms_file.filename == "":
            return jsonify(
                {
                    "error": True,
                    "error_message": "Uploading file failed",
                }
            )

        # Detect if this is direct-message.js or direct-message-group.js
        content = dms_file.read()
        expected_dm_start = b"window.YTD.direct_messages.part0 = "
        expected_dm_headers_start = b"window.YTD.direct_message_headers.part0 = "
        expected_dm_group_start = b"window.YTD.direct_messages_group.part0 = "
        expected_dm_group_headers_start = (
            b"window.YTD.direct_message_group_headers.part0 = "
        )
        if content.startswith(expected_dm_start):
            dm_type = "dms"
            json_string = content[len(expected_dm_start) :]
        elif content.startswith(expected_dm_headers_start):
            dm_type = "dms"
            json_string = content[len(expected_dm_headers_start) :]
        elif content.startswith(expected_dm_group_start):
            dm_type = "groups"
            json_string = content[len(expected_dm_group_start) :]
        elif content.startswith(expected_dm_group_headers_start):
            dm_type = "groups"
            json_string = content[len(expected_dm_group_headers_start) :]
        else:
            return jsonify(
                {
                    "error": True,
                    "error_message": "This does not appear to be a direct-messages.js, direct-message-headers.js, direct-messages-group.js, or direct-message-group-headers.js file",
                }
            )

        # Save to disk
        if dm_type == "dms":
            job_type = "delete_dms"
            filename = os.path.join("/var/bulk_dms", f"dms-{current_user.id}.json")
        elif dm_type == "groups":
            job_type = "delete_dm_groups"
            filename = os.path.join("/var/bulk_dms", f"groups-{current_user.id}.json")

        with open(filename, "wb") as f:
            f.write(json_string)

        try:
            conversations = json.loads(json_string)
        except:
            os.unlink(filename)
            return jsonify(
                {
                    "error": True,
                    "error_message": "Failed parsing JSON object",
                }
            )

        if type(conversations) != list:
            os.unlink(filename)
            return jsonify(
                {
                    "error": True,
                    "error_message": "JSON object expected to be a list",
                }
            )

        for obj in conversations:
            if type(obj) != dict:
                os.unlink(filename)
                return jsonify(
                    {
                        "error": True,
                        "error_message": "JSON object expected to be a list of dicts",
                    }
                )
            if "dmConversation" not in obj:
                os.unlink(filename)
                return jsonify(
                    {
                        "error": True,
                        "error_message": "JSON object expected to be a list of dicts that contain 'dmConversation' fields",
                    }
                )
            dm_conversation = obj["dmConversation"]
            if "messages" not in dm_conversation:
                os.unlink(filename)
                return jsonify(
                    {
                        "error": True,
                        "error_message": "JSON object expected to be a list of dicts that contain 'dmConversations' fields that contain 'messages' fields",
                    }
                )

        # Create a new delete_dms job
        add_job(job_type, current_user.id, worker_jobs.funcs)
        return jsonify({"error": False})

    else:
        return "Bad request", 400


## Admin API routes


@app.route("/admin_api/jobs")
@admin_required
def admin_api_jobs(current_user):
    """
    Get information about current jobs
    """
    active_jobs = db_session.scalars(
        select(JobDetails)
        .where(JobDetails.status == "active")
        .order_by(JobDetails.started_timestamp)
    ).fetchall()

    with db_engine.connect() as conn:
        pending_jobs_count = conn.execute(
            text(
                """SELECT
	COUNT(id)
FROM
	job_details
WHERE
	status = 'pending'
	AND (job_type = 'fetch' OR job_type = 'delete')
	AND (scheduled_timestamp IS NULL OR scheduled_timestamp <= NOW())
    """
            )
        ).scalar()
        scheduled_jobs_count = conn.execute(
            text(
                """SELECT
	COUNT(id)
FROM
	job_details
WHERE
	status = 'pending'
	AND (job_type = 'fetch' OR job_type = 'delete')
	AND scheduled_timestamp > NOW()
    """
            )
        ).scalar()

    def to_client(job):
        duration = datetime.now() - job.started_timestamp
        duration = str(duration).split(".")[0]

        user = db_session.scalar(select(User).where(User.id == job.user_id))
        if user:
            twitter_username = user.twitter_screen_name
            twitter_link = f"https://twitter.com/{user.twitter_screen_name}"
        else:
            twitter_username = None
            twitter_link = None

        try:
            redis_job = RQJob.fetch(job.redis_id, connection=conn)
            redis_status = redis_job.get_status(refresh=True)
        except:
            redis_status = "N/A"

        return {
            "id": job.id,
            "user_id": job.user_id,
            "twitter_username": twitter_username,
            "twitter_link": twitter_link,
            "job_type": job.job_type,
            "data": json.loads(job.data),
            "status": job.status,
            "duration": duration,
            "redis_status": redis_status,
        }

    return jsonify(
        {
            "active_jobs": [to_client(job) for job in active_jobs],
            "pending_jobs_count": pending_jobs_count,
            "scheduled_jobs_count": scheduled_jobs_count,
        }
    )


@app.route("/admin_api/users")
@admin_required
def admin_api_users(current_user):
    """
    Get information about users
    """
    users = db_session.scalars(
        select(User).order_by(User.twitter_screen_name)
    ).fetchall()
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

    impersonating_twitter_id = session.get("impersonating_twitter_id")
    impersonating_twitter_username = None

    if impersonating_twitter_id:
        impersonating_user = db_session.scalar(
            select(User).where(User.twitter_id == impersonating_twitter_id)
        )
        if impersonating_user:
            impersonating_twitter_username = impersonating_user.twitter_screen_name

    return jsonify(
        {
            "impersonating_twitter_id": impersonating_twitter_id,
            "impersonating_twitter_username": impersonating_twitter_username,
            "active_users": to_client(active_users),
            "paused_users": to_client(paused_users),
            "blocked_users": to_client(blocked_users),
        }
    )


@app.route("/admin_api/users/<user_id>")
@admin_required
def admin_api_users_user(current_user, user_id):
    """
    Get information about a specific user
    """
    user = db_session.scalar(select(User).where(User.id == user_id))
    if not user:
        return jsonify(False)

    # Get fascist tweets that this user has liked
    fascist_likes = db_session.scalars(
        select(Like)
        .where(Like.user_id == user_id)
        .where(Like.is_fascist == True)
        .order_by(Like.created_at.desc())
    ).fetchall()
    fascist_tweet_urls = [
        f"https://twitter.com/semiphemeral/status/{like.twitter_id}"
        for like in fascist_likes
    ]

    return jsonify(
        {
            "twitter_username": user.twitter_screen_name,
            "paused": user.paused,
            "blocked": user.blocked,
            "fascist_tweet_urls": fascist_tweet_urls,
        }
    )


@app.route("/admin_api/users/impersonate", methods=["POST"])
@admin_required
def admin_api_users_impersonate(current_user):
    """
    Impersonate a user
    """
    try:
        data = json.loads(request.data)
    except Exception as e:
        log(None, f"Error parsing JSON: {e}")
        return jsonify({"error": True, "error_message": "Error parsing JSON"})

    # Validate
    valid = _api_validate({"twitter_id": str}, data)
    if not valid["valid"]:
        return valid["message"], 400

    if data["twitter_id"] == "0":
        session["impersonating_twitter_id"] = None
        log(
            None,
            f"Stopping impersonating user @{current_user.twitter_screen_name}",
        )
    else:
        impersonating_user = db_session.scalar(
            select(User).where(User.twitter_id == data["twitter_id"])
        )
        if impersonating_user:
            session["impersonating_twitter_id"] = data["twitter_id"]
            log(None, f"Impersonating user @{impersonating_user.twitter_screen_name}")
        else:
            log(None, f"Cannot find user to impersonate")

    return jsonify(True)


@app.route("/admin_api/fascists", methods=["GET", "POST"])
@admin_required
def admin_api_fascists(current_user):
    """
    GET: Get a list of fascists
    POST: Add or delete fascists
    """
    if request.method == "GET":
        fascists = db_session.scalars(select(Fascist).order_by(Fascist.username))

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

        return jsonify({"fascists": to_client(fascists)})

    elif request.method == "POST":
        try:
            data = json.loads(request.data)
        except Exception as e:
            log(None, f"Error parsing JSON: {e}")
            return jsonify({"error": True, "error_message": "Error parsing JSON"})

        # Validate
        valid = _api_validate({"action": str}, data)
        if not valid["valid"]:
            return valid["message"], 400

        if data["action"] != "create" and data["action"] != "delete":
            return "action must be 'create' or 'delete'", 400

        user = db_session.scalar(
            select(User).where(User.twitter_id == session.get("twitter_id"))
        )

        api = tweepy_api_v1_1(user)

        if data["action"] == "create":
            valid = _api_validate(
                {"action": str, "username": str, "comment": str}, data
            )
            if not valid["valid"]:
                return valid["message"], 400

            try:
                response = api.get_user(screen_name=data["username"])
            except:
                return jsonify(False)

            fascist_twitter_user_id = response.id_str

            # If a fascist with this username already exists, just update the comment
            fascist = db_session.scalar(
                select(Fascist).where(Fascist.username == data["username"])
            )
            if fascist:
                fascist.twitter_id = fascist_twitter_user_id
                fascist.comment = data["comment"]
                db_session.add(fascist)
                db_session.commit()
                return jsonify(True)

            # Create the fascist
            fascist = Fascist(
                username=data["username"],
                twitter_id=fascist_twitter_user_id,
                comment=data["comment"],
            )
            db_session.add(fascist)
            db_session.commit()

            # Mark all the tweets from this user as is_fascist=True
            db_session.execute(
                update(Like)
                .values(is_fascist=True)
                .where(Like.author_id == fascist_twitter_user_id)
            )

            # Make sure the fascist is blocked
            add_job(
                "block", None, worker_jobs.funcs, {"twitter_username": data["username"]}
            )
            return jsonify(True)

        elif data["action"] == "delete":
            valid = _api_validate({"action": str, "username": str}, data)
            if not valid["valid"]:
                return valid["message"], 400

            # Delete the fascist
            fascist = db_session.scalar(
                select(Fascist).where(Fascist.username == data["username"])
            )
            if fascist:
                db_session.delete(fascist)
                db_session.commit()

            try:
                response = api.get_user(screen_name=data["username"])
            except:
                return jsonify(False)

            fascist_twitter_user_id = response.id_str

            # Mark all the tweets from this user as is_fascist=False
            db_session.execute(
                update(Like)
                .values(is_fascist=False)
                .where(Like.author_id == fascist_twitter_user_id)
            )

            return jsonify(True)

    else:
        return "Bad request", 400


@app.route("/admin_api/tips")
@admin_required
def admin_api_tips(current_user):
    """
    Get all the tips
    """
    users = {}
    tips = db_session.scalars(
        select(Tip).where(Tip.paid == True).order_by(Tip.timestamp.desc())
    ).fetchall()
    for tip in tips:
        if tip.user_id not in users:
            user = db_session.scalar(select(User).where(User.id == tip.user_id))
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

    return jsonify({"tips": to_client(tips)})
