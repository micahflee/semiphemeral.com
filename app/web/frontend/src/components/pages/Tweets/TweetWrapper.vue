<template>
  <div class="tweet-wrapper">
    <div class="info">
      <label>
        <input type="checkbox" v-bind:checked="excludeFromDeletion" />
        <span v-if="excludeFromDeletion">Excluded from deletion</span>
        <span v-else>Staged for deletion</span>
      </label>
      <div class="stats">
        {{ tweet.retweet_count }} retweets,
        {{ tweet.favorite_count }} likes,
        <a
          target="_blank"
          v-bind:href="twitterPermalink"
        >permalink</a>
      </div>
    </div>
    <Tweet v-bind:id="statusId"></Tweet>
  </div>
</template>

<style scoped>
.tweet-wrapper {
  display: inline-block;
  width: 500px;
  margin-right: 10px;
}
</style>

<script>
import { Tweet } from "vue-tweet-embed";

export default {
  props: ["tweet", "userScreenName"],
  data: function() {
    return {
      excludeFromDeletion: false
    };
  },
  created: function() {
    this.excludeFromDeletion = this.tweet.exclude;
  },
  computed: {
    twitterPermalink: function() {
      return (
        "https://twitter.com/" +
        this.userScreenName +
        "/status/" +
        this.tweet.status_id
      );
    },
    statusId: function() {
      return this.tweet.status_id;
    }
  },
  components: {
    Tweet: Tweet
  }
};
</script>