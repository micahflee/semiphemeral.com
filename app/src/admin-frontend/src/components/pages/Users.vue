<template>
  <div>
    <h1>Users</h1>

    <div v-if="activeUsers.length > 0">
      <h2>{{ activeUsers.length }} active users</h2>
      <ul>
        <li v-for="user in activeUsers">
          <User v-bind:user="user"></User>
        </li>
      </ul>
    </div>

    <div v-if="pausedUsers.length > 0">
      <h2>{{ pausedUsers.length }} paused users</h2>
      <ul>
        <li v-for="user in pausedUsers">
          <User v-bind:user="user"></User>
        </li>
      </ul>
    </div>

    <div v-if="blockedUsers.length > 0">
      <h2>{{ blockedUsers.length }} blocked users</h2>
      <ul>
        <li v-for="user in blockedUsers">
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
  data: function() {
    return {
      loading: false,
      activeUsers: [],
      pausedUsers: [],
      blockedUsers: []
    };
  },
  created: function() {
    this.fetchUsers();
  },
  methods: {
    fetchUsers: function() {
      var that = this;
      this.loading = true;

      // Get lists of users
      fetch("/admin_api/users")
        .then(function(response) {
          if (response.status !== 200) {
            console.log(
              "Error fetching users, status code: " + response.status
            );
            that.loading = false;
            return;
          }
          response.json().then(function(data) {
            that.loading = false;
            if (data["active_users"]) that.activeUsers = data["active_users"];
            else that.activeUsers = [];

            if (data["paused_users"]) that.pausedUsers = data["paused_users"];
            else that.pausedUsers = [];

            if (data["blocked_users"])
              that.blockedUsers = data["blocked_users"];
            else that.blockedUsers = [];
          });
        })
        .catch(function(err) {
          console.log("Error fetching users", err);
          that.loading = false;
        });
    }
  },
  components: {
    User: User
  }
};
</script>