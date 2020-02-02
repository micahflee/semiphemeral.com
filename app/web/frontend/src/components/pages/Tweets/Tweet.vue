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
        {{ tweet.like_count }} likes,
        <a
          target="_blank"
          v-bind:href="twitterPermalink"
        >permalink</a>
      </div>
    </div>
    <div ref="embeddedTweet" v-bind:id="embeddedTweetId"></div>
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
let addScriptPromise = 0;
function addScript() {
  if (!addScriptPromise) {
    const s = document.createElement("script");
    s.setAttribute("src", "https://platform.twitter.com/widgets.js");
    document.body.appendChild(s);
    addScriptPromise = new Promise(resolve => {
      s.onload = () => {
        resolve(window.twttr);
      };
    });
  }
  return addScriptPromise;
}

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
  mounted: function() {
    this.$nextTick(this.loadTweet);
  },
  updated: function() {
    this.$nextTick(this.loadTweet);
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
    embeddedTweetId: function() {
      return "tweet-" + this.tweet.status_id;
    }
  },
  methods: {
    loadTweet: function() {
      var that = this;
      Promise.resolve(window.twttr ? window.twttr : addScript()).then(function(
        twttr
      ) {
        twttr.widgets.createTweetEmbed(
          that.tweet.status_id,
          that.$refs.embeddedTweet,
          { dnt: true }
        );
      });
    }
  }
};
</script>