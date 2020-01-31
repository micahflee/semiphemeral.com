import Vue from 'vue';

// Load modules
require('./pages/dashboard.js');
require('./pages/tweets.js');
require('./pages/settings.js');
require('./pages/tip.js');
require('./pages/thanks.js');

// Main navigation components
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
            <span class="user">
                <img v-if="userScreenName" v-bind:src="userProfileUrl" v-bind:title="logoutTitle" />
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
        lastFetch: false
    },
    created: function () {
        this.getUser()
    },
    methods: {
        selectPage: function (pageComponent) {
            this.currentPageComponent = pageComponent
        },
        getUser: function () {
            var that = this;
            fetch("/api/user")
                .then(function (response) {
                    if (response.status !== 200) {
                        console.log('Error fetching user, status code: ' + response.status);
                        return;
                    }
                    response.json().then(function (data) {
                        that.userScreenName = data['user_screen_name'];
                        that.userProfileUrl = data['user_profile_url'];
                        that.lastFetch = data['last_fetch'];
                    })
                })
                .catch(function (err) {
                    console.log("Error fetching user", err)
                })
        }
    }
})