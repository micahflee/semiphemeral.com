Vue.component('settings', {
    data: function () {
        return {
            deleteTweets: this.$root.settingsDeleteTweets,
            tweetsDaysThreshold: this.$root.settingsTweetsDaysThreshold,
            tweetsRetweetThreshold: this.$root.settingsTweetsRetweetThreshold,
            tweetsLikeThreshold: this.$root.settingsTweetsLikeThreshold,
            tweetsThreadsThreshold: this.$root.settingsTweetsThreadsThreshold,
            retweetsLikes: this.$root.settingsRetweetsLikes,
            retweetsLikesDeleteRetweets: this.$root.settingsRetweetsLikesDeleteRetweets,
            retweetsLikesRetweetsThreshold: this.$root.settingsRetweetsLikesRetweetsThreshold,
            retweetsLikesDeleteLikes: this.$root.settsettingsRetweetsLikesDeleteLikes,
            retweetsLikesLikesThreshold: this.$root.settingsRetweetsLikesLikesThreshold,
        }
    },
    template: `
        <div class="page settings">
            <h1>Choose what you'd like Semiphemeral to automatically delete</h1>
            <form method="post" action="/settings">
            <p>
                <label class="checkbox">
                    <input type="checkbox" class="delete-tweets-checkbox" name="delete_tweets" v-model="deleteTweets" />
                    Delete old tweets
                </label>
            </p>
            <fieldset class="delete-tweets-fieldset">
                <legend>Tweets</legend>
                <p>
                    Delete tweets older than
                    <input class="small" type="number" min="0"  name="tweets_days_threshold" v-model="tweetsDaysThreshold" \>
                    days
                </p>
                <p>
                    Unless they have at least
                    <input class="small" type="number" min="0"  name="tweets_retweet_threshold" v-model="tweetsRetweetThreshold" \>
                    retweets
                </p>
                <p>
                    Or at least
                    <input class="small" type="number" min="0"  name="tweets_like_threshold" v-model="tweetsLikeThreshold" \>
                    likes
                </p>
                <p>
                    <label class="checkbox">
                        <input type="checkbox" name="tweets_threads_threshold" v-model="tweetsThreadsThreshold" />
                        Don't delete tweets that are part of a thread that contains at least one tweet that meets these thresholds
                    </label>
                </p>
            </fieldset>

            <p>
                <label class="checkbox">
                <input type="checkbox" class="retweets-likes-checkbox" name="retweets_likes" v-model="retweetsLikes" />
                Unretweet and unlike old tweets
                </label>
            </p>

            <fieldset class="retweets-likes-fieldset">
                <legend>Retweets and likes</legend>

                <p>
                    <label class="checkbox">
                        <input type="checkbox" name="retweets_likes_delete_retweets" v-model="retweetsLikesDeleteRetweets" />
                        Unretweet tweets
                    </label>
                    older than
                    <input class="small" type="number" min="0"  name="retweets_likes_retweets_threshold" v-model="retweetsLikesRetweetsThreshold" \>
                    days
                </p>

                <p>
                    <label class="checkbox">
                        <input type="checkbox" name="retweets_likes_delete_likes" v-model="retweetsLikesDeleteLikes" />
                        Unlike tweets
                    </label>
                    older than
                    <input class="small" type="number" min="0"  name="retweets_likes_likes_threshold" v-model="retweetsLikesLikesThreshold" \>
                    days
                </p>

            </fieldset>

            <p><input type="submit" value="Save" /></p>
            </form>
        </div>
    `
})