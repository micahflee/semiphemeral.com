Vue.component('nav-button', {
    props: ["currentPageComponent", "buttonText", "pageComponent"],
    computed: {
        isActive: function () {
            return this.currentPageComponent == this.pageComponent
        }
    },
    template: `
        <button
            v-on:click="$emit('select-page')"
            v-bind:class="{ active: isActive }">
            {{ buttonText }}
        </button>
    `
})

Vue.component('nav-bar', {
    props: ['currentPageComponent', 'userScreenName', 'userProfileUrl'],
    data: function () {
        return {
            buttons: [
                { buttonText: "Dashboard", pageComponent: "dashboard" },
                { buttonText: "Tweets", pageComponent: "tweets" },
                { buttonText: "Settings", pageComponent: "settings" },
                { buttonText: "Tip", pageComponent: "tip" },
            ]
        }
    },
    computed: {
        logoutTitle: function () {
            return "Logged in as @" + this.userScreenName
        }
    },
    template: `
        <div class="nav">
            <span class="logo"><a href="/"><img src="/static/img/logo-small.png" /></a></span>
            <ul>
                <li v-for="button in buttons">
                    <nav-button
                        v-bind="{
                            currentPageComponent: currentPageComponent,
                            buttonText: button.buttonText,
                            pageComponent: button.pageComponent
                        }"
                        v-on:select-page="$emit('select-page', button.pageComponent)">
                    </nav-button>
                </li>
            </ul>
            <span class="user" v-if="userScreenName">
                <img v-bind:src="userProfileUrl" v-bind:title="logoutTitle" />
                <span><a href="/auth/logout">Log out</a></span>
            </span>
        </div>
    `
})

var app = new Vue({
    el: "#app",
    data: {
        currentPageComponent: "dashboard",
        userScreenName: false,
        userProfileUrl: false,
        settingsDeleteTweets: false,
        settingsTweetsDaysThreshold: false,
        settingsTweetsRetweetThreshold: false,
        settingsTweetsLikeThreshold: false,
        settingsTweetsThreadsThreshold: false,
        settingsRetweetsLikes: false,
        settingsRetweetsLikesDeleteRetweets: false,
        settingsRetweetsLikesRetweetsThreshold: false,
        settingsRetweetsLikesDeleteLikes: false,
        settingsRetweetsLikesLikesThreshold: false,
        lastFetch: false
    },
    methods: {
        selectPage: function (pageComponent) {
            this.currentPageComponent = pageComponent
        }
    }
})

// Fetch the logged in user
fetch("/api/get_user")
    .then(function (response) {
        if (response.status !== 200) {
            console.log('Error fetching user, status code: ' + response.status);
            return;
        }
        response.json().then(function (data) {
            app.userScreenName = data['user']['twitter_screen_name'];
            app.userProfileUrl = data['user']['profile_image_url'];
            app.settingsDeleteTweets = data['settings']['delete_tweets'];
            app.settingsTweetsDaysThreshold = data['settings']['tweets_days_threshold'];
            app.settingsTweetsRetweetThreshold = data['settings']['tweets_retweet_threshold'];
            app.settingsTweetsLikeThreshold = data['settings']['tweets_like_threshold'];
            app.settingsTweetsThreadsThreshold = data['settings']['tweets_threads_threshold'];
            app.settingsRetweetsLikes = data['settings']['retweets_likes'];
            app.settingsRetweetsLikesDeleteRetweets = data['settings']['retweets_likes_delete_retweets'];
            app.settingsRetweetsLikesRetweetsThreshold = data['settings']['retweets_likes_retweets_threshold'];
            app.settingsRetweetsLikesDeleteLikes = data['settings']['retweets_likes_delete_likes'];
            app.settingsRetweetsLikesLikesThreshold = data['settings']['retweets_likes_likes_threshold'];
            app.lastFetch = data['last_fetch'];
        })
    })
    .catch(function (err) {
        console.log("Error fetching user", err)
    })