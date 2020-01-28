Vue.component('tweet', {
    data: function () {
        return {
            excludeFromDeletion: false
        }
    },
    props: ["tweet"],
    created: function () {
        this.excludeFromDeletion = this.tweet.exclude;

        // Display the tweet
        var el = document.getElementById(this.tweetId);
        twttr.widgets.createTweet(tweet, el, { 'dnt': true });
    },
    computed: {
        tweetId: function () {
            return "tweet-" + this.tweet.status_id
        }
    },
    template: `
        <div>
            <div class="info">
                <label>
                    <input type="checkbox" v-bind="excludeFromDeletion" />
                    <span v-if="excludeFromDeletion">Excluded from deletion</span>
                    <span v-else>Staged for deletion</span>
                </label>
                <div class="stats">{{ tweet.retweet_count }} retweets, {{ tweet.favorite_count }} likes</div>
            </div>
            <div v-bind:class="tweetId"></div>
        </div>
    `
})

Vue.component('tweets', {
    data: function () {
        return {
            loading: false,
            tweets: [],
            ids: []
        }
    },
    created: function () {
        this.fetchTweets()
    },
    methods: {
        fetchTweets: function () {
            var that = this;
            this.loading = true;

            // Get all saved tweets
            fetch("/api/tweets")
                .then(function (response) {
                    if (response.status !== 200) {
                        console.log('Error fetching tweets, status code: ' + response.status);
                        return;
                    }
                    response.json().then(function (data) {
                        that.tweets = data['tweets'];
                        that.ids = [];
                        for (var id in that.tweets) {
                            that.ids.push(id);
                        }
                        that.loading = false;
                    })
                })
                .catch(function (err) {
                    console.log("Error fetching tweets", err)
                    that.loading = false;
                })
        }
    },
    template: `
        <div class="page tweets">
            <h1>
                Choose which tweets should never get automatically deleted
                <img
                    class="refresh"
                    v-on:click="fetchTweets()"
                    src="/static/img/refresh.png"
                    alt="Refresh" title="Refresh" />
            </h1>

            <template v-if="loading">
                <p><img src="/static/img/loading.gif" alt="Loading" /></p>
            </template>
            <template v-else>
                <ul v-for="tweet in tweets">
                    <tweet v-bind="tweet"></tweet>
                </ul>
            </template>
        </div>
    `
})