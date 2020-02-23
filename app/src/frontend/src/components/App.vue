<style>
html {
  position: relative;
  min-height: 100%;
}

body {
  margin: 0 0 25px;
  padding: 10px;
  font-family: sans;
}

p {
  line-height: 150%;
}

li {
  line-height: 150%;
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

a:link,
a:visited {
  color: #28404f;
  text-decoration: underline;
}

a:active,
a:hover {
  color: #5d8fad;
  text-decoration: none;
}

footer {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 25px;
  width: 100%;
  overflow: hidden;
  text-align: right;
  font-size: 0.7em;
}

footer p {
  margin: 0 10px;
}
</style>

<template>
  <div>
    <NavBar
      v-bind="{
            userScreenName: userScreenName,
            userProfileUrl: userProfileUrl }"
    ></NavBar>
    <router-view v-bind="{
      userScreenName: userScreenName
    }"></router-view>
    <footer>
      <p>
        <a href="/privacy">Privacy</a>
      </p>
    </footer>
  </div>
</template>

<script>
import NavBar from "./layout/NavBar.vue";

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
    NavBar: NavBar
  }
};
</script>