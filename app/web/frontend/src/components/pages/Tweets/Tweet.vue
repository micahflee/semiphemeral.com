<template>
  <div class="tweet-wrapper">
    <div class="info">
      <label>
        <input ref="excludeCheckbox" type="checkbox" v-model="exclude" v-on:click="toggleExclude()" />
        <span v-if="exclude" class="excluded">Excluded from deletion</span>
        <span v-else>Staged for deletion</span>
        <span v-if="loading">
          <img src="/static/img/loading.gif" title="Loading" />
        </span>
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
.excluded {
  font-weight: bold;
}
.stats {
  font-size: 0.8em;
  color: #666666;
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
      loading: false,
      exclude: null,
      previousStatusId: null
    };
  },
  created: function() {
    this.exclude = this.tweet.exclude;
  },
  mounted: function() {
    this.$nextTick(this.embedTweet);
  },
  beforeUpdate: function() {
    // If the tweet div id is "tweet-123", this will set previousStatusId to "123"
    this.previousStatusId = this.$refs.embeddedTweet
      .getAttribute("id")
      .split("-")[1];
  },
  updated: function() {
    this.$nextTick(this.embedTweet);
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
    embedTweet: function() {
      var that = this;

      // If the tweet itself hasn't changed, no need to re-embed it
      if (this.previousStatusId == this.tweet.status_id) {
        return;
      }

      // Delete everything in the tweet div
      while (this.$refs.embeddedTweet.firstChild) {
        this.$refs.embeddedTweet.removeChild(
          this.$refs.embeddedTweet.firstChild
        );
      }

      // Embed the tweet
      Promise.resolve(window.twttr ? window.twttr : addScript()).then(function(
        twttr
      ) {
        twttr.widgets.createTweetEmbed(
          that.tweet.status_id,
          that.$refs.embeddedTweet,
          { dnt: true }
        );
      });
    },
    toggleExclude: function() {
      console.log("exclude", this.exclude);

      var that = this;
      this.loading = true;
      this.$refs.excludeCheckbox.disabled = true;

      fetch("/api/tweets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status_id: that.tweet.status_id,
          exclude: that.exclude
        })
      })
        .then(function(response) {
          that.loading = false;
          that.$refs.excludeCheckbox.disabled = false;
        })
        .catch(function(err) {
          console.log("Error toggling exclude", err);
          that.loading = false;
          that.$refs.excludeCheckbox.disabled = false;
        });
    }
  }
};
</script>