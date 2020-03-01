<template>
  <div>
    <a v-bind:href="profileLink">{{ user['twitter_screen_name'] }}</a>
    <span v-if="user.last_fetch">last fetch {{ lastFetch }}</span>
    <span v-if="user.blocked">(<router-link v-bind:to="infoLink">info</router-link>)</span>
  </div>
</template>

<script>
export default {
  props: ["user"],
  computed: {
    profileLink: function() {
      return "https://twitter.com/" + this.user["twitter_screen_name"];
    },
    lastFetch: function() {
      return this.humanReadableTimestamp(this.user["last_fetch"]);
    },
    infoLink: function() {
      return "/admin_api/users/" + this.user.id
    }
  },
  methods: {
    humanReadableTimestamp: function(timestamp) {
      var date = new Date(timestamp * 1000);
      return date.toLocaleDateString() + " at " + date.toLocaleTimeString();
    }
  }
};
</script>