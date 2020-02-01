<template>
  <NavBar
    v-on:select-page="selectPage"
    v-bind="{
            currentPageComponent: currentPageComponent,
            userScreenName: userScreenName,
            userProfileUrl: userProfileUrl }"
  ></NavBar>
  <component v-on:select-page="selectPage" v-bind:is="currentPageComponent"></component>
</template>

<script>
import NavBar from "./Layout/NavBar.vue";
import Dashboard from "./Dashboard.vue";
import Tweets from "./Tweets.vue";
import Settings from "./Settings.vue";
import Tip from "./Tip.vue";
import Thanks from "./Thanks.vue";

export default {
  data: {
    currentPageComponent: "Dashboard",
    userScreenName: false,
    userProfileUrl: false,
    lastFetch: false
  },
  created: function() {
    this.getUser();
  },
  methods: {
    selectPage: function(pageComponent) {
      this.currentPageComponent = pageComponent;
    },
    getUser: function() {
      var that = this;
      fetch("/api/user")
        .then(function(response) {
          if (response.status !== 200) {
            console.log("Error fetching user, status code: " + response.status);
            return;
          }
          response.json().then(function(data) {
            that.userScreenName = data["user_screen_name"];
            that.userProfileUrl = data["user_profile_url"];
            that.lastFetch = data["last_fetch"];
          });
        })
        .catch(function(err) {
          console.log("Error fetching user", err);
        });
    }
  }
};
</script>