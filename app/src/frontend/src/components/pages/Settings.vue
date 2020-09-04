<style scoped>
input.small {
  width: 3em;
}
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

.disabled {
  opacity: 50%;
}

.dm-note {
  font-size: 0.8em;
  color: #666666;
}
</style>

<template>
  <div>
    <h1>Choose what you'd like Semiphemeral to automatically delete</h1>

    <template v-if="loading">
      <p>
        <img src="/static/img/loading.gif" alt="Loading" />
      </p>
    </template>
    <template v-else>
      <form v-on:submit.prevent="onSubmit">
        <p>
          <label class="checkbox">
            <input type="checkbox" v-model="deleteTweets" />
            Delete old tweets
          </label>
        </p>
        <fieldset v-bind:class="deleteTweets ? '' : 'disabled'">
          <legend>Tweets</legend>
          <p>
            Delete tweets older than
            <input
              type="number"
              class="small"
              min="0"
              v-model="tweetsDaysThreshold"
              v-bind:disabled="!deleteTweets"
            />
            days
          </p>
          <p>
            <label>
              <input
                type="checkbox"
                v-model="tweetsEnableRetweetThreshold"
                v-bind:disabled="!deleteTweets"
              />
              Unless they have at least
            </label>
            <input
              type="number"
              class="small"
              min="0"
              v-model="tweetsRetweetThreshold"
              v-bind:disabled="!deleteTweets || !tweetsEnableRetweetThreshold"
            />
            retweets
          </p>
          <p>
            <label>
              <input
                type="checkbox"
                v-model="tweetsEnableLikeThreshold"
                v-bind:disabled="!deleteTweets"
              />
              Or at least
            </label>
            <input
              type="number"
              class="small"
              min="0"
              v-model="tweetsLikeThreshold"
              v-bind:disabled="!deleteTweets || !tweetsEnableLikeThreshold"
            />
            likes
          </p>
          <p>
            <label>
              <input
                type="checkbox"
                v-model="tweetsThreadsThreshold"
                v-bind:disabled="!deleteTweets"
              />
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

        <fieldset v-bind:class="retweetsLikes ? '' : 'disabled'">
          <legend>Retweets and likes</legend>

          <p>
            <label>
              <input
                type="checkbox"
                v-model="retweetsLikesDeleteRetweets"
                v-bind:disabled="!retweetsLikes"
              />
              Unretweet tweets
            </label>
            older than
            <input
              type="number"
              class="small"
              min="0"
              v-model="retweetsLikesRetweetsThreshold"
              v-bind:disabled="!retweetsLikes"
            />
            days
          </p>

          <p>
            <label>
              <input
                type="checkbox"
                v-model="retweetsLikesDeleteLikes"
                v-bind:disabled="!retweetsLikes"
              />
              Unlike tweets
            </label>
            older than
            <input
              type="number"
              class="small"
              min="0"
              v-model="retweetsLikesLikesThreshold"
              v-bind:disabled="!retweetsLikes"
            />
            days
          </p>
        </fieldset>

        <template v-if="isDMAppAuthenticated">
          <p>
            <label>
              <input type="checkbox" v-model="directMessages" />
              Delete old direct messages
            </label>
          </p>

          <fieldset v-bind:class="directMessages ? '' : 'disabled'">
            <legend>Direct messages</legend>

            <p>
              Delete direct messages older than
              <input
                type="number"
                class="small"
                min="0"
                max="29"
                v-model="directMessagesThreshold"
                v-bind:disabled="!directMessages"
              />
              days
            </p>

            <p class="dm-note">
              Twitter only allows Semiphemeral access to the last 30 days of DMs, so you have to delete older DMs manually.
              <router-link to="/dms">Learn more</router-link>&nbsp;about how this works.
            </p>
          </fieldset>
        </template>
        <template v-else>
          <fieldset>
            <legend class="disabled">Direct messages</legend>
            <p>
              Semiphemeral can automatically delete your old direct messages for you. To enable this feature you must allow Semiphemeral access to your DMs.
              <button
                v-on:click="authenticateDMs()"
              >Give Semiphemeral access to my DMs</button>
            </p>
          </fieldset>
        </template>

        <p v-if="hasFetched">
          <label>
            <input type="checkbox" v-model="downloadAllTweets" />
            Force Semiphemeral to download all of my tweets again next time, instead of just the newest ones
          </label>
        </p>

        <p>
          <input v-bind:disabled="loading" type="submit" value="Save" />
        </p>

        <div class="danger">
          <h2>Danger Zone</h2>
          <p>
            <button
              v-on:click="deleteAccount()"
            >Delete my Semiphemeral account, and all data associated with it</button>
          </p>
        </div>
      </form>
    </template>
  </div>
</template>

<script>
export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      hasFetched: false,
      deleteTweets: false,
      tweetsDaysThreshold: false,
      tweetsEnableRetweetThreshold: false,
      tweetsRetweetThreshold: false,
      tweetsEnableLikeThreshold: false,
      tweetsLikeThreshold: false,
      tweetsThreadsThreshold: false,
      retweetsLikes: false,
      retweetsLikesDeleteRetweets: false,
      retweetsLikesRetweetsThreshold: false,
      retweetsLikesDeleteLikes: false,
      retweetsLikesLikesThreshold: false,
      directMessages: false,
      directMessagesThreshold: false,
      isDMAppAuthenticated: false,
      downloadAllTweets: false,
    };
  },
  created: function () {
    this.getSettings();
  },
  methods: {
    getSettings: function () {
      var that = this;
      fetch("/api/settings")
        .then(function (response) {
          if (response.status !== 200) {
            console.log(
              "Error fetching settings, status code: " + response.status
            );
            return;
          }
          response.json().then(function (data) {
            that.hasFetched = data["has_fetched"];
            that.deleteTweets = data["delete_tweets"];
            that.tweetsDaysThreshold = data["tweets_days_threshold"];
            that.tweetsEnableRetweetThreshold =
              data["tweets_enable_retweet_threshold"];
            that.tweetsRetweetThreshold = data["tweets_retweet_threshold"];
            that.tweetsEnableLikeThreshold =
              data["tweets_enable_like_threshold"];
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
            that.directMessages = data["direct_messages"];
            that.directMessagesThreshold = data["direct_messages_threshold"];
            that.isDMAppAuthenticated = data["is_dm_app_authenticated"];
          });
        })
        .catch(function (err) {
          console.log("Error fetching user", err);
        });
    },
    onSubmit: function () {
      var that = this;
      this.loading = true;
      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "save",
          delete_tweets: this.deleteTweets,
          tweets_days_threshold: Number(this.tweetsDaysThreshold),
          tweets_enable_retweet_threshold: this.tweetsEnableRetweetThreshold,
          tweets_retweet_threshold: Number(this.tweetsRetweetThreshold),
          tweets_enable_like_threshold: this.tweetsEnableLikeThreshold,
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
          direct_messages: this.directMessages,
          direct_messages_threshold: Number(this.directMessagesThreshold),
          download_all_tweets: this.downloadAllTweets,
        }),
      })
        .then(function (response) {
          that.loading = false;
          that.getSettings();
        })
        .catch(function (err) {
          console.log("Error updating settings", err);
          that.loading = false;
        });
    },
    deleteAccount: function () {
      if (confirm("All of your data will be deleted. Are you totally sure?")) {
        fetch("/api/settings/delete_account", { method: "POST" })
          .then(function (response) {
            document.location = "/";
          })
          .catch(function (err) {
            console.log("Error deleting account", err);
          });
      }
    },
    authenticateDMs: function () {
      var that = this;
      this.loading = true;
      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "authenticate_dms",
        }),
      })
        .then(function (response) {
          if (response.status !== 200) {
            console.log(
              "Error authenticating with Twitter, status code: " +
                response.status
            );
            that.loading = false;
            return;
          }
          response.json().then(function (data) {
            if (data["error"]) {
              alert(
                "Error authenticating with Twitter:\n" + data["error_message"]
              );
              that.loading = false;
            } else {
              // Redirect to authenticate
              document.location = data["redirect_url"];
            }
          });
        })
        .catch(function (err) {
          console.log("Error authenticating with Twitter", err);
          that.loading = false;
        });
    },
  },
};
</script>