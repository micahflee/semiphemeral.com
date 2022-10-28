<script setup>
import { ref, nextTick, onBeforeUpdate, onUpdated, watch } from "vue"

const props = defineProps({
  tweet: Object,
  userScreenName: String
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

const loading = ref(false)
const exclude = ref(props['tweet'].exclude)
const previousStatusId = ref(null)
const error = ref("")

const twitterPermalink = "https://twitter.com/" + props['userScreenName'] + "/status/" + props['tweet'].status_id
const embeddedTweetId = "tweet-" + props['tweet'].status_id

function embedTweet() {
  // If the tweet itself hasn't changed, no need to re-embed it
  if (previousStatusId.value == props["tweet"]["status_id"]) {
    return
  }

  // Make sure the exclude checkbox is updated
  exclude.value = null; // set it to null first, to avoid POSTing to the API
  exclude.value = props['tweet'].exclude

  // Delete everything in the tweet div
  while ($refs.embeddedTweet.firstChild) {
    $refs.embeddedTweet.removeChild($refs.embeddedTweet.firstChild)
  }

  // Embed the tweet
  Promise.resolve(window.twttr ? window.twttr : addScript()).then(function (
    twttr
  ) {
    twttr.widgets.createTweetEmbed(
      props['tweet'].status_id,
      $refs.embeddedTweet,
      { dnt: true }
    )
  })
}

nextTick(embedTweet)

onBeforeUpdate(() => {
  // If the tweet div id is "tweet-123", this will set previousStatusId to "123"
  previousStatusId.value = $refs.embeddedTweet
    .getAttribute("id")
    .split("-")[1]
})

onUpdated(() => {
  nextTick(embedTweet)
})

watch(exclude, (newExclude, oldExclude) => {
  // Skip if this is the first time
  if (newExclude == null || oldExclude == null) {
    return
  }
  if (newExclude) {
    this.$emit("exclude-true")
  } else {
    this.$emit("exclude-false")
  }

  loading.value = true
  error.value = ""
  $refs.excludeCheckbox.disabled = true

  fetch("/api/tweets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      status_id: props['tweet'].status_id,
      exclude: exclude.value,
    })
  })
    .then(function (response) {
      loading.value = false
      $refs.excludeCheckbox.disabled = false
    })
    .catch(function (err) {
      console.log("Error toggling exclude", err)
      loading.value = false
      $refs.excludeCheckbox.disabled = false

      // Toggle back
      var oldExclude = exclude.value
      exclude.value = null
      exclude.value = !oldExclude
      error.value = "Error toggling exclude"
    });
})
</script>

<template>
  <div class="tweet-wrapper">
    <div class="info">
      <label>
        <input ref="excludeCheckbox" type="checkbox" v-model="exclude" />
        <span v-if="exclude" class="excluded">Tweet excluded from deletion</span>
        <span v-else>It's okay if this tweet gets deleted</span>
        <span v-if="loading">
          <img src="/images/loading.gif" title="Loading" />
        </span>
        <span v-if="error != ''" class="error">{{ error }}</span>
      </label>
      <div class="stats">
        {{ tweet.retweet_count }} retweets,
        {{ tweet.like_count }} likes,
        <a target="_blank" v-bind:href="twitterPermalink">permalink</a>
      </div>
    </div>
    <div ref="embeddedTweet" v-bind:id="embeddedTweetId"></div>
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

.excluded {
  font-weight: bold;
}

.stats {
  font-size: 0.8em;
  color: #666666;
}

.error {
  color: #cc0000;
}
</style>