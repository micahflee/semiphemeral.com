<template>
  <div>
    <div class="info">
      <label>
        <input type="checkbox" v-bind:checked="excludeFromDeletion" />
        <span v-if="excludeFromDeletion">Excluded from deletion</span>
        <span v-else>Staged for deletion</span>
      </label>
      <div class="stats">{{ tweet.retweet_count }} retweets, {{ tweet.favorite_count }} likes</div>
    </div>
    <div v-bind:id="tweetId"></div>
  </div>
</template>

<script>
export default {
  data: function() {
    return {
      excludeFromDeletion: false
    };
  },
  props: ["tweet"],
  created: function() {
    this.excludeFromDeletion = this.tweet.exclude;
  },
  mounted: function() {
    var that = this;
    this.$nextTick(function() {
      // TODO: Display the tweet
      //   twttr.widgets.createTweet(
      //     that.tweet.status_id,
      //     document.getElementById(that.tweetId),
      //     { dnt: true }
      //   );
    });
  },
  computed: {
    tweetId: function() {
      return "tweet-" + this.tweet.status_id;
    }
  }
};
</script>