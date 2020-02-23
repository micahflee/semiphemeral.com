<template>
  <div>
    <a v-bind:href="profileLink">{{ user['twitter_screen_name'] }}</a>
    <span v-if="user.last_fetch">last fetch {{ lastFetch }}</span>
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