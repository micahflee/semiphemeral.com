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
  margin: 0 0 150px 0; /* big margin at the bottom to make space for controls */
  padding: 0;
}

li {
  display: inline-block;
  vertical-align: top;
}
</style>

<template>
  <div class="page">
    <h1>Choose which tweets should never get automatically deleted</h1>

    <p>You may need to disable your adblocker for semiphemeral.com for the embedded tweets to show up properly (this website doesn't have ads).</p>

    <template v-if="loading">
      <p>
        <img src="/static/img/loading.gif" alt="Loading" />
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
          <span v-for="pageNumber in pageNumbers">
            <PageButton
              v-bind="{
                pageNumber: pageNumber,
                currentPage: page
              }"
              v-on:select-page="filterTweets(pageNumber)"
            ></PageButton>
          </span>
        </div>
      </div>

      <ul>
        <li v-for="id in pageIndices">
          <Tweet
            v-bind="{
              tweet: tweets[id],
              userScreenName: userScreenName
            }"
            v-on:exclude-true="changeExclude(id, true)"
            v-on:exclude-false="changeExclude(id, false)"
          ></Tweet>
        </li>
      </ul>
    </template>
  </div>
</template>

<script>
import Tweet from "./Tweets/Tweet.vue";
import PageButton from "./Tweets/PageButton.vue";

export default {
  props: ["userScreenName"],
  data: function() {
    return {
      loading: false,
      tweets: [],
      filteredIndices: [], // Indices for tweets after applying filter
      pageIndices: [], // Indices of tweets on the current page
      filterQuery: "",
      showReplies: true,
      page: 0,
      numPages: 1,
      countPerPage: 50,
      pageNumbers: [],
      info: ""
    };
  },
  computed: {
    numberOfTweetsStagedForDeletion: function() {
      var count = 0;
      for (var i = 0; i < this.tweets.length; i++) {
        if (!this.tweets[i].exclude) {
          count++;
        }
      }
      return count;
    }
  },
  created: function() {
    this.fetchTweets();
  },
  watch: {
    showReplies: function() {
      this.filterTweets();
    },
    filterQuery: function() {
      this.filterTweets();
    }
  },
  methods: {
    fetchTweets: function() {
      var that = this;
      this.loading = true;

      // Get all saved tweets
      fetch("/api/tweets")
        .then(function(response) {
          if (response.status !== 200) {
            console.log(
              "Error fetching tweets, status code: " + response.status
            );
            return;
          }
          response.json().then(function(data) {
            that.tweets = data["tweets"];
            that.filterTweets();
            that.loading = false;
          });
        })
        .catch(function(err) {
          console.log("Error fetching tweets", err);
          that.loading = false;
        });
    },
    filterTweets: function(page = 0) {
      if (page == "previous") {
        this.page--;
      } else if (page == "next") {
        this.page++;
      } else {
        this.page = page;
      }

      // filteredIndices is a list of tweets array indices that match the filter settings
      this.filteredIndices = [];
      for (var i = 0; i < this.tweets.length; i++) {
        if (
          this.tweets[i]["text"]
            .toLowerCase()
            .includes(this.filterQuery.toLowerCase())
        ) {
          if (
            this.showReplies ||
            (!this.showReplies && !this.tweets[i]["is_reply"])
          ) {
            this.filteredIndices.push(i);
          }
        }
      }

      // Calculate number of pages
      this.numPages = Math.ceil(
        this.filteredIndices.length / this.countPerPage
      );
      if (this.page >= this.numPages) {
        this.page = 0;
      }

      // Make the page numbers boxes
      this.pageNumbers = [];
      if (this.page > 0) {
        this.pageNumbers.push("previous");
      }
      for (var i = this.page - 3; i <= this.page + 3; i++) {
        if (i >= 0 && i <= this.numPages - 1) {
          this.pageNumbers.push(i);
        }
      }
      if (this.page < this.numPages - 1) {
        this.pageNumbers.push("next");
      }

      // pageIndices is a list of tweets array indices to get displayed on the current page
      this.pageIndices = [];
      for (
        var i = this.page * this.countPerPage;
        i < (this.page + 1) * this.countPerPage;
        i++
      ) {
        if (i < this.filteredIndices.length) {
          this.pageIndices.push(this.filteredIndices[i]);
        }
      }

      // The info text box
      this.updateInfo();
    },
    updateInfo: function() {
      this.info =
        "Page " +
        this.commaFormatted(this.page) +
        " of " +
        this.commaFormatted(this.numPages) +
        " | ";
      if (this.filteredIndices.length != this.tweets.length) {
        this.info +=
          "Filtering to " +
          this.filteredIndices.length +
          " of " +
          this.tweets.length +
          " tweets | ";
      } else {
        this.info += this.tweets.length + " tweets | ";
      }
      this.info +=
        this.numberOfTweetsStagedForDeletion + " tweets staged for deletion";
    },
    commaFormatted: function(x) {
      return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    },
    changeExclude: function(id, exclude) {
      this.tweets[id].exclude = exclude;
      this.updateInfo();
    }
  },
  components: {
    Tweet: Tweet,
    PageButton: PageButton
  }
};
</script>