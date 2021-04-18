<style scoped>
.column {
  display: inline-block;
  vertical-align: top;
}
</style>

<template>
  <div>
    <h1>Users</h1>

    <template v-if="impersonatingTwitterUsername != null">
      <p>
        You are impersonating twitter user
        <a target="_blank" v-bind:href="impersonatingLink"
          >@{{ impersonatingTwitterUsername }}</a
        >.
        <button v-on:click="stopImpersonating">Stop impersonating.</button>
      </p>
    </template>

    <div v-if="activeUsers.length > 0" class="column">
      <h2>{{ activeUsers.length }} active users</h2>
      <ul>
        <li v-for="(user, index) in activeUsers" v-bind:key="index">
          <User v-bind:user="user"></User>
        </li>
      </ul>
    </div>

    <div v-if="pausedUsers.length > 0" class="column">
      <h2>{{ pausedUsers.length }} paused users</h2>
      <ul>
        <li v-for="(user, index) in pausedUsers" v-bind:key="index">
          <User v-bind:user="user"></User>
        </li>
      </ul>
    </div>

    <div v-if="blockedUsers.length > 0" class="column">
      <h2>{{ blockedUsers.length }} blocked users</h2>
      <ul>
        <li v-for="(user, index) in blockedUsers" v-bind:key="index">
          <User v-bind:user="user"></User>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
import User from "./Users/User.vue";

export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      impersonatingTwitterUsername: null,
      activeUsers: [],
      pausedUsers: [],
      blockedUsers: [],
    };
  },
  created: function () {
    this.fetchUsers();
  },
  computed: {
    impersonatingLink: function () {
      return "https://twitter.com/" + this.impersonatingTwitterUsername;
    },
  },
  methods: {
    fetchUsers: function () {
      var that = this;
      this.loading = true;

      // Get lists of users
      fetch("/admin_api/users")
        .then(function (response) {
          if (response.status !== 200) {
            console.log(
              "Error fetching users, status code: " + response.status
            );
            that.loading = false;
            return;
          }
          response.json().then(function (data) {
            that.loading = false;
            that.impersonatingTwitterUsername =
              data["impersonating_twitter_username"];

            if (data["active_users"]) that.activeUsers = data["active_users"];
            else that.activeUsers = [];

            if (data["paused_users"]) that.pausedUsers = data["paused_users"];
            else that.pausedUsers = [];

            if (data["blocked_users"])
              that.blockedUsers = data["blocked_users"];
            else that.blockedUsers = [];
          });
        })
        .catch(function (err) {
          console.log("Error fetching users", err);
          that.loading = false;
        });
    },
    stopImpersonating: function () {
      var that = this;
      this.loading = true;

      fetch("/admin_api/users/impersonate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          twitter_id: "0",
        }),
      })
        .then(function (response) {
          that.fetchUsers();
        })
        .catch(function (err) {
          console.log("Error", err);
        });
    },
  },
  components: {
    User: User,
  },
};
</script>