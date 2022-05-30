<script>
let addScriptPromise = 0;
function addScript() {
  if (!addScriptPromise) {
    const s = document.createElement("script");
    s.setAttribute("src", "https://platform.twitter.com/widgets.js");
    document.body.appendChild(s);
    addScriptPromise = new Promise((resolve) => {
      s.onload = () => {
        resolve(window.twttr);
      };
    });
  }
  return addScriptPromise;
}

export default {
  props: ["statusId", "permalink"],
  mounted: function () {
    this.$nextTick(this.embedTweet);
  },
  computed: {
    embeddedTweetId: function () {
      return "tweet-" + this.statusId;
    },
  },
  methods: {
    embedTweet: function () {
      // Delete everything in the tweet div
      while (this.$refs.embeddedTweet.firstChild) {
        this.$refs.embeddedTweet.removeChild(
          this.$refs.embeddedTweet.firstChild
        );
      }

      // Embed the tweet
      var that = this;
      Promise.resolve(window.twttr ? window.twttr : addScript()).then(function (
        twttr
      ) {
        twttr.widgets.createTweetEmbed(
          that.statusId,
          that.$refs.embeddedTweet,
          { dnt: true }
        );
      });
    },
  },
};
</script>

<template>
  <div class="tweet-wrapper">
    <div ref="embeddedTweet" v-bind:id="embeddedTweetId"></div>
    <p>
      <a target="_blank" v-bind:href="permalink">View on Twitter</a>
    </p>
  </div>
</template>

<style scoped>
.tweet-wrapper {
  display: inline-block;
  width: 380px;
  max-width: 100%;
  border: 1px solid #f0f0f0;
  border-radius: 5px;
  padding: 5px 5px 0 5px;
  margin: 0 10px 10px 0;
}
.error {
  color: #cc0000;
}
</style>