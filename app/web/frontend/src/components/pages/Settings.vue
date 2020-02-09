<style scoped>
.danger {
  margin-top: 100px;
  opacity: 80%;
  border: 2px solid #df2e2e;
  border-radius: 10px;
  padding: 5px 10px;
  display: inline-block;
}
.danger button {
  background-color: #df2e2e;
  border: none;
  color: white;
  padding: 5px 20px;
  text-align: center;
  text-decoration: none;
  display: inline-block;
  cursor: pointer;
  font-weight: bold;
  border-radius: 5px;
}
.danger h2 {
  margin: 5px;
}
.danger p {
  margin: 5px;
}
</style>

<template>
  <div>
    <h1>Choose what you'd like Semiphemeral to automatically delete</h1>
    <form v-on:submit.prevent="onSubmit">
      <p>
        <label class="checkbox">
          <input type="checkbox" v-model="deleteTweets" />
          Delete old tweets
        </label>
      </p>
      <fieldset v-if="deleteTweets">
        <legend>Tweets</legend>
        <p>
          Delete tweets older than
          <input type="number" min="0" v-model="tweetsDaysThreshold" />
          days
        </p>
        <p>
          Unless they have at least
          <input type="number" min="0" v-model="tweetsRetweetThreshold" />
          retweets
        </p>
        <p>
          Or at least
          <input type="number" min="0" v-model="tweetsLikeThreshold" />
          likes
        </p>
        <p>
          <label>
            <input type="checkbox" v-model="tweetsThreadsThreshold" />
            Don't delete tweets that are part of a thread that contains at least one tweet that meets these thresholds
          </label>
        </p>
      </fieldset>

      <p>
        <label>
          <input type="checkbox" v-model="retweetsLikes" />
          Unretweet and unlike old tweets
        </label>
      </p>

      <fieldset v-if="retweetsLikes">
        <legend>Retweets and likes</legend>

        <p>
          <label>
            <input type="checkbox" v-model="retweetsLikesDeleteRetweets" />
            Unretweet tweets
          </label>
          older than
          <input type="number" min="0" v-model="retweetsLikesRetweetsThreshold" />
          days
        </p>

        <p>
          <label>
            <input type="checkbox" v-model="retweetsLikesDeleteLikes" />
            Unlike tweets
          </label>
          older than
          <input type="number" min="0" v-model="retweetsLikesLikesThreshold" />
          days
        </p>
      </fieldset>

      <p v-if="hasFetched">
        <label>
          <input type="checkbox" v-model="downloadAllTweets" />
          Force Semiphemeral to download all of my tweets again next time, instead of just the newest ones
        </label>
      </p>

      <p>
        <input v-bind:disabled="loading" type="submit" value="Save" />
        <img v-if="loading" src="/static/img/loading.gif" alt="Loading" />
      </p>

      <div class="danger">
        <h2>Danger Zone</h2>
        <p>
          <button v-on:click="deleteAccount()">Delete my account, and all data associated with it</button>
        </p>
      </div>
    </form>
  </div>
</template>

<script>
export default {
  props: ["userScreenName"],
  data: function() {
    return {
      loading: false,
      hasFetched: false,
      deleteTweets: false,
      tweetsDaysThreshold: false,
      tweetsRetweetThreshold: false,
      tweetsLikeThreshold: false,
      tweetsThreadsThreshold: false,
      retweetsLikes: false,
      retweetsLikesDeleteRetweets: false,
      retweetsLikesRetweetsThreshold: false,
      retweetsLikesDeleteLikes: false,
      retweetsLikesLikesThreshold: false,
      downloadAllTweets: false
    };
  },
  created: function() {
    this.getSettings();
  },
  methods: {
    getSettings: function() {
      var that = this;
      fetch("/api/settings")
        .then(function(response) {
          if (response.status !== 200) {
            console.log(
              "Error fetching settings, status code: " + response.status
            );
            return;
          }
          response.json().then(function(data) {
            that.hasFetched = data["has_fetched"];
            that.deleteTweets = data["delete_tweets"];
            that.tweetsDaysThreshold = data["tweets_days_threshold"];
            that.tweetsRetweetThreshold = data["tweets_retweet_threshold"];
            that.tweetsLikeThreshold = data["tweets_like_threshold"];
            that.tweetsThreadsThreshold = data["tweets_threads_threshold"];
            that.retweetsLikes = data["retweets_likes"];
            that.retweetsLikesDeleteRetweets =
              data["retweets_likes_delete_retweets"];
            that.retweetsLikesRetweetsThreshold =
              data["retweets_likes_retweets_threshold"];
            that.retweetsLikesDeleteLikes = data["retweets_likes_delete_likes"];
            that.retweetsLikesLikesThreshold =
              data["retweets_likes_likes_threshold"];
          });
        })
        .catch(function(err) {
          console.log("Error fetching user", err);
        });
    },
    onSubmit: function() {
      var that = this;
      this.loading = true;
      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          delete_tweets: this.deleteTweets,
          tweets_days_threshold: Number(this.tweetsDaysThreshold),
          tweets_retweet_threshold: Number(this.tweetsRetweetThreshold),
          tweets_like_threshold: Number(this.tweetsLikeThreshold),
          tweets_threads_threshold: this.tweetsThreadsThreshold,
          retweets_likes: this.retweetsLikes,
          retweets_likes_delete_retweets: this.retweetsLikesDeleteRetweets,
          retweets_likes_retweets_threshold: Number(
            this.retweetsLikesRetweetsThreshold
          ),
          retweets_likes_delete_likes: this.retweetsLikesDeleteLikes,
          retweets_likes_likes_threshold: Number(
            this.retweetsLikesLikesThreshold
          ),
          download_all_tweets: this.downloadAllTweets
        })
      })
        .then(function(response) {
          that.loading = false;
          that.getSettings();
        })
        .catch(function(err) {
          console.log("Error updating settings", err);
          that.loading = false;
        });
    },
    deleteAccount: function() {
      if (confirm("All of your data will be deleted. Are you totally sure?")) {
        fetch("/api/settings/delete_account", { method: "POST" })
          .then(function(response) {
            document.location = "/";
          })
          .catch(function(err) {
            console.log("Error deleting account", err);
          });
      }
    }
  }
};
</script>