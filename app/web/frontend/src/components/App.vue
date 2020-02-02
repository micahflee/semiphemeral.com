<template>
  <div>
    <NavBar
      v-on:select-page="selectPage"
      v-bind="{
            currentPageComponent: currentPageComponent,
            userScreenName: userScreenName,
            userProfileUrl: userProfileUrl }"
    ></NavBar>
    <component v-on:select-page="selectPage" v-bind:is="currentPageComponent"></component>
  </div>
</template>

<style>
body {
  font-family: sans;
}

#app {
  max-width: 1000px;
  margin: 0 auto;
  font-size: 0.9em;
}

h1 {
  font-size: 1.3em;
}

h2 {
  font-size: 1.1em;
}

img.refresh {
  margin-left: 1em;
  height: 15px;
  cursor: pointer;
}
</style>

<script>
import NavBar from "./layout/NavBar.vue";
import Dashboard from "./pages/Dashboard.vue";
import Tweets from "./pages/Tweets.vue";
import Settings from "./pages/Settings.vue";
import Tip from "./pages/Tip.vue";
import Thanks from "./pages/Thanks.vue";

export default {
  data: function() {
    return {
      currentPageComponent: "Dashboard",
      userScreenName: false,
      userProfileUrl: false,
      lastFetch: false
    };
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
  },
  components: {
    NavBar: NavBar,
    Dashboard: Dashboard,
    Tweets: Tweets,
    Settings: Settings,
    Tip: Tip,
    Thanks: Thanks
  }
};
</script>