Vue.component('settings', {
    data: function () {
        return {
            loading: false,
            deleteTweets: this.$root.settingsDeleteTweets,
            tweetsDaysThreshold: this.$root.settingsTweetsDaysThreshold,
            tweetsRetweetThreshold: this.$root.settingsTweetsRetweetThreshold,
            tweetsLikeThreshold: this.$root.settingsTweetsLikeThreshold,
            tweetsThreadsThreshold: this.$root.settingsTweetsThreadsThreshold,
            retweetsLikes: this.$root.settingsRetweetsLikes,
            retweetsLikesDeleteRetweets: this.$root.settingsRetweetsLikesDeleteRetweets,
            retweetsLikesRetweetsThreshold: this.$root.settingsRetweetsLikesRetweetsThreshold,
            retweetsLikesDeleteLikes: this.$root.settingsRetweetsLikesDeleteLikes,
            retweetsLikesLikesThreshold: this.$root.settingsRetweetsLikesLikesThreshold,
        }
    },
    methods: {
        "onSubmit": function () {
            this.loading = true
            fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    delete_tweets: this.deleteTweets,
                    tweets_days_threshold: this.tweetsDaysThreshold,
                    tweets_retweet_threshold: this.tweetsRetweetThreshold,
                    tweets_like_threshold: this.tweetsLikeThreshold,
                    tweets_threads_threshold: this.tweetsThreadsThreshold,
                    retweets_likes: this.retweetsLikes,
                    retweets_likes_delete_retweets: this.retweetsLikesDeleteRetweets,
                    retweets_likes_retweets_threshold: this.retweetsLikesRetweetsThreshold,
                    retweets_likes_delete_likes: this.retweetsLikesDeleteLikes,
                    retweets_likes_likes_threshold: this.retweetsLikesLikesThreshold
                })
            })
                .then(function (response) {
                    this.loading = false
                    // TODO: Force the root component to re-fetch
                })
                .catch(function (err) {
                    console.log("Error updating settings", err)
                    this.loading = false
                })
        }
    },
    template: `
        <div class="page settings">
            <h1>Choose what you'd like Semiphemeral to automatically delete</h1>
            <form v-on:submit.prevent="onSubmit">
            <p>
                <label class="checkbox">
                    <input type="checkbox" v-model="deleteTweets" />
                    Delete old tweets
                </label>
            </p>
            <fieldset v-if="deleteTweets">
                <legend>Tweets</legend>
                <p>
                    Delete tweets older than
                    <input type="number" min="0" v-model="tweetsDaysThreshold" \>
                    days
                </p>
                <p>
                    Unless they have at least
                    <input type="number" min="0" v-model="tweetsRetweetThreshold" \>
                    retweets
                </p>
                <p>
                    Or at least
                    <input type="number" min="0" v-model="tweetsLikeThreshold" \>
                    likes
                </p>
                <p>
                    <label>
                        <input type="checkbox" v-model="tweetsThreadsThreshold" />
                        Don't delete tweets that are part of a thread that contains at least one tweet that meets these thresholds
                    </label>
                </p>
            </fieldset>

            <p>
                <label>
                    <input type="checkbox" v-model="retweetsLikes" />
                    Unretweet and unlike old tweets
                </label>
            </p>

            <fieldset v-if="retweetsLikes">
                <legend>Retweets and likes</legend>

                <p>
                    <label>
                        <input type="checkbox" v-model="retweetsLikesDeleteRetweets" />
                        Unretweet tweets
                    </label>
                    older than
                    <input type="number" min="0" v-model="retweetsLikesRetweetsThreshold" \>
                    days
                </p>

                <p>
                    <label>
                        <input type="checkbox" v-model="retweetsLikesDeleteLikes" />
                        Unlike tweets
                    </label>
                    older than
                    <input type="number" min="0" v-model="retweetsLikesLikesThreshold" \>
                    days
                </p>

            </fieldset>

            <p>
                <input v-bind:disabled="loading" type="submit" value="Save" />
                <img v-if="loading" src="/static/img/loading.gif" alt="Loading" />
            </p>
            </form>
        </div>
    `
})