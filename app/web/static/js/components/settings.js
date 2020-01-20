Vue.component('settings', {
    template: `
        <div class="page settings">
            <h1>Settings</h1>
            <form method="post" action="/settings">
            <p>
                <label class="checkbox">
                <input type="checkbox" class="delete-tweets-checkbox" name="delete_tweets" {% if delete_tweets %}checked="checked"{% endif %} />
                Delete old tweets
                </label>
            </p>
            <fieldset class="delete-tweets-fieldset">
                <legend>Tweets</legend>
                <p>
                    Delete tweets older than
                    <input class="small" type="number" min="0"  name="tweets_days_threshold" value="{{ tweets_days_threshold }}" \>
                    days
                </p>
                <p>
                    Unless they have at least
                    <input class="small" type="number" min="0"  name="tweets_retweet_threshold" value="{{ tweets_retweet_threshold }}" \>
                    retweets
                </p>
                <p>
                    Or at least
                    <input class="small" type="number" min="0"  name="tweets_like_threshold" value="{{ tweets_like_threshold }}" \>
                    likes
                </p>
                <p>
                    <label class="checkbox">
                        <input type="checkbox" name="tweets_threads_threshold" {% if tweets_threads_threshold %}checked="checked"{% endif %} />
                        Don't delete tweets that are part of a thread that contains at least one tweet that meets these thresholds
                    </label>
                </p>
            </fieldset>

            <p>
                <label class="checkbox">
                <input type="checkbox" class="retweets-likes-checkbox" name="retweets_likes" {% if retweets_likes %}checked="checked"{% endif %} />
                Unretweet and unlike old tweets
                </label>
            </p>

            <fieldset class="retweets-likes-fieldset">
                <legend>Retweets and likes</legend>

                <p>
                    <label class="checkbox">
                        <input type="checkbox" name="retweets_likes_delete_retweets" {% if retweets_likes_delete_retweets %}checked="checked"{% endif %} />
                        Unretweet tweets
                    </label>
                    older than
                    <input class="small" type="number" min="0"  name="retweets_likes_retweets_threshold" value="{{ retweets_likes_retweets_threshold }}" \>
                    days
                </p>

                <p>
                    <label class="checkbox">
                        <input type="checkbox" name="retweets_likes_delete_likes" {% if retweets_likes_delete_likes %}checked="checked"{% endif %} />
                        Unlike tweets
                    </label>
                    older than
                    <input class="small" type="number" min="0"  name="retweets_likes_likes_threshold" value="{{ retweets_likes_likes_threshold }}" \>
                    days
                </p>

            </fieldset>

            <p><input type="submit" value="Save" /></p>
            </form>
        </div>
    `
})