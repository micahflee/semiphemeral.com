<style scoped>
ul.buttons {
  list-style: none;
  padding: 0;
  margin-left: 20px;
}

button.start,
button.download {
  background-color: #4caf50;
  border: none;
  color: white;
  padding: 5px 20px;
  text-align: center;
  text-decoration: none;
  display: inline-block;
  cursor: pointer;
  font-weight: bold;
  border-radius: 5px;
  margin: 0 0 5px 0;
}

button.pause,
button.reactivate {
  background-color: #624caf;
  border: none;
  color: white;
  padding: 5px 20px;
  text-align: center;
  text-decoration: none;
  display: inline-block;
  cursor: pointer;
  font-weight: bold;
  border-radius: 5px;
  margin: 0 0 5px 0;
}

ul.jobs {
  list-style: none;
  padding: 0;
}

.warning {
  color: #624caf;
  font-weight: bold;
  font-style: italic;
}
.center {
  text-align: center;
}
</style>

<template>
  <div>
    <h1>
      Semiphemeral Dashboard
      <img
        class="refresh"
        v-on:click="fetchJobs()"
        src="/static/img/refresh.png"
        alt="Refresh"
        title="Refresh"
      />
    </h1>

    <template v-if="loading">
      <p>
        <img src="/static/img/loading.gif" alt="Loading" />
      </p>
    </template>
    <template v-else>
      <div v-if="settingBlocked">
        <p class="center">
          <img
            src="/static/img/refuse.png"
            alt="We reserve the right to refuse service to anyone"
          />
        </p>
        <p>
          Semiphemeral is an antifascist service. In order to prevent fascists
          from using this free privacy service which I develop in my spare time,
          Semiphemeral keeps track of Twitter accounts used by prominent
          racists, misogynists, antisemites, homophobes, neo-Nazis, and other
          fascists.
        </p>
        <p>
          <strong
            >In the last six months, you have liked
            {{ fascistTweets.length }} tweets from fascist influencers.</strong
          >
          You have been blocked by
          <a href="https://twitter.com/semiphemeral">@semiphemeral</a>, so your
          account has been temporarily disabled.
        </p>
        <p></p>

        <p>You were blocked because you liked these tweets:</p>
        <FascistTweet
          v-for="(tweet, index) in fascistTweets"
          v-bind:statusId="tweet.status_id"
          v-bind:permalink="tweet.permalink"
          v-bind:key="index"
        ></FascistTweet>

        <template v-if="fascistTweets.length > 10">
          <p>
            Because you've recently liked more than 10 tweets from prominent
            fascists, you don't have the option to automatically unblock
            yourself. If you oppose fascism and think that you've been blocked
            unfairly or by mistake, you can appeal by writing an email to
            hi@semiphemeral.com (make sure to mention your Twitter username in
            the email).
          </p>

          <p>
            <button class="reactivate" v-on:click="reactivateAccount">
              I'm no longer blocked
            </button>
          </p>
        </template>
        <template v-else>
          <p>
            If you oppose fascism and think you've been blocked unfairly or by
            mistake, you can unlike these tweets (so you don't get automatically
            blocked again) and then click the button below to unblock yourself:
          </p>

          <p>
            <button class="reactivate" v-on:click="unblockAccount">
              I've unliked these tweets so unblock me
            </button>
          </p>

          <p>
            <button class="reactivate" v-on:click="reactivateAccount">
              I'm no longer blocked, reactivate my account
            </button>
          </p>
        </template>
      </div>
      <div v-else>
        <div v-if="state == 'A'">
          <p>
            Before you delete your old tweets, Semiphemeral needs to download a
            copy of your Twitter history. While you're waiting, make sure your
            <router-link to="/settings">settings</router-link>&nbsp;are exactly
            as you want them.
          </p>
        </div>

        <div v-if="state == 'B'">
          <p>
            You finished downloading a copy of your Twitter history on
            <em>{{ mostRecentFetchFinished }}</em
            >, and Semiphemeral is currently <strong>paused</strong>. Before you
            proceed:
          </p>
          <ul>
            <li>
              If you want,
              <router-link to="/export">export</router-link>&nbsp;a spreadsheet
              of your tweets before you delete them
            </li>
            <li v-if="state == 'B'">
              If you haven't already, make sure your
              <router-link to="/settings">settings</router-link>&nbsp;are
              exactly as you want them
            </li>
            <li>
              <strong>
                Make sure you have manually chosen which of your old
                <router-link to="/tweets">tweets</router-link>&nbsp;you want to
                prevent from getting deleted
              </strong>
            </li>
          </ul>

          <p>When you're ready:</p>
          <ul class="buttons">
            <li>
              <button class="start" v-on:click="startSemiphemeral">
                Start Semiphemeral
              </button>
              or
            </li>
            <li>
              <button class="download" v-on:click="downloadHistory">
                Download my Twitter history again
              </button>
            </li>
          </ul>
        </div>

        <div v-if="state == 'C'">
          <p>
            Semiphemeral is
            <strong>active</strong>.
            <button class="pause" v-on:click="pauseSemiphemeral">
              Pause Semiphemeral
            </button>
          </p>
          <p
            v-if="
              !settingDeleteTweets &&
              !settingRetweetsLikes &&
              !settingDirectMessages
            "
            class="warning"
          >
            Warning: Your settings are configured to not delete any tweets,
            retweets, likes, or direct messages. Go
            <router-link to="/settings">change your settings</router-link
            >&nbsp;if you want Semiphemeral to delete your old tweets.
          </p>
        </div>

        <h2 v-if="activeJobs.length > 0 || pendingJobs.length > 0">
          Current status
        </h2>
        <ul v-if="activeJobs.length > 0" class="jobs">
          <li v-for="(job, index) in activeJobs" v-bind:key="index">
            <Job v-bind:job="job"></Job>
          </li>
        </ul>
        <ul v-if="pendingJobs.length > 0" class="jobs">
          <li v-for="(job, index) in pendingJobs" v-bind:key="index">
            <Job v-bind:job="job"></Job>
          </li>
        </ul>

        <h2 v-if="finishedJobs.length > 0">Log</h2>
        <ul v-if="finishedJobs.length > 0" class="jobs">
          <li v-for="(job, index) in finishedJobs" v-bind:key="index">
            <Job v-bind:job="job"></Job>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script>
import Job from "./Dashboard/Job.vue";
import FascistTweet from "./Dashboard/FascistTweet.vue";

export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      activeJobs: [],
      pendingJobs: [],
      finishedJobs: [],
      settingPaused: null,
      settingBlocked: null,
      settingDeleteTweets: null,
      settingRetweetsLikes: null,
      settingDirectMessages: null,
      fascistTweets: [],
    };
  },
  computed: {
    state: function () {
      // There are 3 states:
      // A: paused, with pending, queued or active jobs (fetching)
      // B: paused, with only finished or cancelled jobs
      // C: not paused
      // More info: https://github.com/micahflee/semiphemeral.com/issues/8
      if (this.settingPaused) {
        if (this.activeJobs.length > 0 || this.pendingJobs.length > 0) {
          return "A";
        } else {
          return "B";
        }
      } else {
        return "C";
      }
    },
    mostRecentFetchFinished: function () {
      var timestamp = 0;
      for (var i = 0; i < this.finishedJobs.length; i++) {
        if (
          this.finishedJobs[i]["job_type"] == "fetch" &&
          this.finishedJobs[i]["finished_timestamp"] > timestamp
        ) {
          timestamp = this.finishedJobs[i]["finished_timestamp"];
        }
      }

      if (timestamp == 0) {
        return "N/A";
      } else {
        var date = new Date(timestamp * 1000);
        return date.toLocaleDateString() + " at " + date.toLocaleTimeString();
      }
    },
  },
  created: function () {
    this.fetchJobs();
  },
  methods: {
    postDashboard: function (action) {
      var that = this;
      this.loading = true;
      fetch("/api/dashboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action }),
      })
        .then(function (response) {
          that.fetchJobs();
        })
        .catch(function (err) {
          console.log("Error", err);
          that.loading = false;
        });
    },
    startSemiphemeral: function () {
      this.postDashboard("start");
    },
    pauseSemiphemeral: function () {
      this.postDashboard("pause");
    },
    downloadHistory: function () {
      this.postDashboard("fetch");
    },
    reactivateAccount: function () {
      var that = this;
      this.loading = true;
      fetch("/api/dashboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "reactivate" }),
      })
        .then(function (response) {
          if (response.status !== 200) {
            console.log("Error reactivating, status code: " + response.status);
            that.loading = false;
            return;
          }
          response.json().then(function (data) {
            console.log(data);
            that.loading = false;
            if (!data["unblocked"]) {
              alert("Nope, you're still blocked");
            } else {
              that.fetchJobs();
            }
          });
        })
        .catch(function (err) {
          console.log("Error", err);
          that.loading = false;
        });
    },
    unblockAccount: function () {
      var that = this;
      this.loading = true;
      fetch("/api/dashboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "unblock" }),
      })
        .then(function (response) {
          if (response.status !== 200) {
            console.log("Error reactivating, status code: " + response.status);
            that.loading = false;
            return;
          }
          response.json().then(function (data) {
            console.log(data);
            that.loading = false;
            if (data["message"]) {
              alert(data["message"]);
            }
          });
        })
        .catch(function (err) {
          console.log("Error", err);
          that.loading = false;
        });
    },
    fetchJobs: function () {
      var that = this;
      this.loading = true;

      // Get list of pending and active jobs
      fetch("/api/dashboard")
        .then(function (response) {
          if (response.status !== 200) {
            console.log("Error fetching jobs, status code: " + response.status);
            that.loading = false;
            return;
          }
          response.json().then(function (data) {
            that.loading = false;
            if (data["active_jobs"]) that.activeJobs = data["active_jobs"];
            else that.activeJobs = [];

            if (data["pending_jobs"]) that.pendingJobs = data["pending_jobs"];
            else that.pendingJobs = [];

            if (data["finished_jobs"])
              that.finishedJobs = data["finished_jobs"];
            else that.finishedJobs = [];

            that.settingPaused = data["setting_paused"];
            that.settingBlocked = data["setting_blocked"];
            that.settingDeleteTweets = data["setting_delete_tweets"];
            that.settingRetweetsLikes = data["setting_retweets_likes"];
            that.settingDirectMessages = data["setting_direct_messages"];
            that.fascistTweets = data["fascist_tweets"];
          });
        })
        .catch(function (err) {
          console.log("Error fetching jobs", err);
          that.loading = false;
        });
    },
  },
  components: {
    Job: Job,
    FascistTweet: FascistTweet,
  },
};
</script>