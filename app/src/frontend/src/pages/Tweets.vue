<script setup>
import { ref, watch } from "vue"
import Tweet from "./Tweets/Tweet.vue"
import PageButton from "./Tweets/PageButton.vue"

const props = defineProps({
  userScreenName: String
})

const loading = ref(false)
const tweets = ref([])
const filteredIndices = ref([]) // Indices for tweets after applying filter
const pageIndices = ref([]) // Indices of tweets on the current page
const filterQuery = ref("")
const showReplies = ref(true)
const page = ref(0)
const numPages = ref(1)
const countPerPage = ref(50)
const pageNumbers = ref([])
const info = ref("")

function numberOfTweetsStagedForDeletion() {
  var count = 0
  for (var i = 0; i < this.tweets.length; i++) {
    if (!tweets[i].exclude) {
      count++
    }
  }
  return count
}

watch(showReplies, (value) => {
  filterTweets()
})

watch(filterQuery, (value) => {
  filterTweets()
})

function fetchTweets() {
  loading.value = true;

  // Get all saved tweets
  fetch("/api/tweets")
    .then(function (response) {
      if (response.status !== 200) {
        console.log(
          "Error fetching tweets, status code: " + response.status
        )
        return
      }
      response.json().then(function (data) {
        tweets.value = data["tweets"]
        filterTweets()
        loading.value = false
      })
    })
    .catch(function (err) {
      console.log("Error fetching tweets", err)
      loading.value = false
    })
}

function filterTweets(pageClicked = 0) {
  if (pageClicked == "previous") {
    page.value--
  } else if (pageClicked == "next") {
    page.value++
  } else {
    page.value = pageClicked
  }

  // filteredIndices is a list of tweets array indices that match the filter settings
  filteredIndices.value = [];
  for (var i = 0; i < tweets.value.length; i++) {
    if (
      tweets.value[i]["text"]
        .toLowerCase()
        .includes(filterQuery.value.toLowerCase())
    ) {
      if (
        showReplies.value ||
        (!showReplies.value && !tweets.value[i]["is_reply"])
      ) {
        filteredIndices.value.push(i)
      }
    }
  }

  // Calculate number of pages
  numPages.value = Math.ceil(
    filteredIndices.value.length / countPerPage.value
  )
  if (page.value >= numPages.value) {
    page.value = 0
  }

  // Make the page numbers boxes
  pageNumbers.value = []
  if (page.value > 0) {
    pageNumbers.value.push("previous")
  }
  for (var i = this.page - 3; i <= this.page + 3; i++) {
    if (i >= 0 && i <= numPages.value - 1) {
      pageNumbers.value.push(i)
    }
  }
  if (page.value < numPages.value - 1) {
    pageNumbers.value.push("next")
  }

  // pageIndices is a list of tweets array indices to get displayed on the current page
  pageIndices.value = []
  for (
    var i = page.value * countPerPage.value;
    i < (page.value + 1) * countPerPage.value;
    i++
  ) {
    if (i < filteredIndices.value.length) {
      pageIndices.value.push(filteredIndices.value[i])
    }
  }

  // The info text box
  this.updateInfo()
}

function updateInfo() {
  info.value =
    "Page " +
    commaFormatted(page.value) +
    " of " +
    commaFormatted(numPages.value) +
    " | "
  if (filteredIndices.value.length != tweets.value.length) {
    info.value +=
      "Filtering to " +
      filteredIndices.value.length +
      " of " +
      tweets.value.length +
      " tweets | "
  } else {
    info.value += tweets.value.length + " tweets | "
  }
  info.value +=
    numberOfTweetsStagedForDeletion.value + " tweets okay to delete"
}

function commaFormatted(x) {
  return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")
}

function changeExclude(id, exclude) {
  tweets.value[id].exclude = exclude
  updateInfo()
}

fetchTweets()
</script>

<template>
  <div class="page">
    <h1>Choose which tweets should never get automatically deleted</h1>

    <p>
      You may need to disable your adblocker for semiphemeral.com for the
      embedded tweets to show up properly (this website doesn't have ads).
    </p>

    <template v-if="loading">
      <p>
        <img src="/images/loading.gif" alt="Loading" />
      </p>
    </template>
    <template v-else>
      <div class="controls">
        <div class="filter">
          <input placeholder="Filter" type="text" v-model="filterQuery" />
        </div>
        <div class="options">
          <label>
            <input type="checkbox" v-model="showReplies" /> Show replies
          </label>
        </div>
        <div class="info">{{ info }}</div>
        <div class="pagination" v-if="this.numPages > 1">
          <span v-for="(pageNumber, index) in pageNumbers" v-bind:key="index">
            <PageButton v-bind="{
              pageNumber: pageNumber,
              currentPage: page,
            }" v-on:select-page="filterTweets(pageNumber)"></PageButton>
          </span>
        </div>
      </div>

      <ul>
        <li v-for="(id, index) in pageIndices" v-bind:key="index">
          <Tweet v-bind="{
            tweet: tweets[id],
            userScreenName: userScreenName,
          }" v-on:exclude-true="changeExclude(id, true)" v-on:exclude-false="changeExclude(id, false)"></Tweet>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.controls {
  display: block;
  position: fixed;
  bottom: 0;
  left: 0;
  z-index: 999;
  background-color: #dae8f1;
  padding: 10px;
  width: 100%;
  border-top: 1px solid #666;
}

.controls .filter input {
  min-width: 90%;
  padding: 5px;
  font-size: 1.2em;
}

.controls .options {
  margin: 0 20px 10px 0;
  color: #666666;
  font-size: 0.8em;
  display: inline-block;
}

.controls .info {
  margin: 0 0 10px 0;
  color: #666666;
  font-size: 0.8em;
  display: inline-block;
}

.controls .pagination {
  margin: 15px 0 0 0;
}

ul {
  list-style: none;
  margin: 0 0 150px 0;
  /* big margin at the bottom to make space for controls */
  padding: 0;
}

li {
  display: inline-block;
  vertical-align: top;
}
</style>