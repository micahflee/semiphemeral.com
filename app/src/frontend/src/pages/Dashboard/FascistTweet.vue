<script setup>
import { nextTick } from 'vue'

const props = defineProps({
  tweet: Object
})

function formatDate() {
  var date = new Date(props.tweet.created_at * 1000)
  return "" + date.getFullYear() +
    "/" + (date.getMonth() + 1) +
    "/" + date.getDate()
}
</script>

<template>
  <div class="tweet-wrapper">
    <div class="info">
      <div class="stats">
        {{ tweet.retweet_count }} retweets,
        {{ tweet.like_count }} likes,
        <a target="_blank" :href="tweet.permalink">see on
          Twitter</a>
      </div>
    </div>
    <div class="tweet-text">{{ tweet.text }}</div>
    <div class="created-at">{{ formatDate() }}</div>
  </div>
</template>

<style scoped>
.tweet-wrapper {
  display: inline-block;
  width: 300px;
  max-width: 100%;
  border: 1px solid #f0f0f0;
  border-radius: 5px;
  padding: 5px 5px 0 5px;
  margin: 0 10px 10px 0;
  overflow: hidden;
}

.stats {
  font-size: 0.8em;
  color: #666666;
}

.created-at {
  font-size: 0.9em;
  color: #666666;
  text-align: right;
}
</style>