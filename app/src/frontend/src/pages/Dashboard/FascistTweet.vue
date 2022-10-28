<script setup>
import { nextTick } from 'vue'

const props = defineProps({
  statusId: String,
  permalink: String
})

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

const embeddedTweetId = "tweet-" + statusId.value;

function embedTweet() {
  // Delete everything in the tweet div
  while ($refs.embeddedTweet.firstChild) {
    $refs.embeddedTweet.removeChild(
      $refs.embeddedTweet.firstChild
    )
  }

  // Embed the tweet
  Promise.resolve(window.twttr ? window.twttr : addScript()).then(function (
    twttr
  ) {
    twttr.widgets.createTweetEmbed(
      statusId.value,
      $refs.embeddedTweet,
      { dnt: true }
    )
  })
}

nextTick(embedTweet)
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