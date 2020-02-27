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
        <h2>Semiphemeral is an antifascist service</h2>
        <p>
          While everyone deserves privacy on social media, not everyone is entitled to get that privacy by using the resources of this free service. You have been blocked by
          <a
            href="https://twitter.com/semiphemeral"
          >@semiphemeral</a>, so your account has been disabled.
        </p>
        <p>Semiphemeral keeps track of the Twitter accounts of prominent authoritarian anti-democratic demagogues and dictators, racists, misogynists, Islamophobes, anti-Semites, homophobes, transphobes, neo-Nazis, hate groups, and fascists and fascist sympathizers. You were probably blocked because you liked a tweet from one of these accounts within the last 6 months.</p>
        <p>If you oppose fascism and think that you've been blocked unfairly or by mistake, you can appeal by writing an email to hi@semiphemeral.com.</p>
        <p>
          <button class="reactivate" v-on:click="reactivateAccount">I'm no longer blocked</button>
        </p>
      </div>
      <div v-else-if="!settingFollowing">
        <p>
          In order to use Semiphemeral, you need to be following
          <a
            href="https://twitter.com/semiphemeral"
          >@semiphemeral</a> on Twitter. Please give us a few minutes to verify that you're following. If it's taking way too long, feel free to contact
          <a
            href="https://twitter.com/semiphemeral"
          >@semiphemeral</a>. DMs are open.
        </p>
      </div>
      <div v-else>
        <div v-if="state == 'A'">
          <p>
            Before you delete your old tweets, Semiphemeral needs to download a copy of your Twitter history. While you're waiting, make sure your
            <router-link to="/settings">settings</router-link>&nbsp;are exactly as you want them.
          </p>
        </div>

        <div v-if="state == 'B'">
          <p>
            You finished downloading a copy of your Twitter history on
            <em>{{ mostRecentFetchFinished }}</em>, and Semiphemeral is currently
            <strong>paused</strong>. Before you proceed:
          </p>
          <ul>
            <li v-if="state == 'B'">
              If you haven't already, make sure your
              <router-link to="/settings">settings</router-link>&nbsp;are exactly as you want them
            </li>
            <li>
              <strong>
                Make sure you have manually chosen which of your old
                <router-link to="/tweets">tweets</router-link>&nbsp;you want to prevent from getting deleted
              </strong>
            </li>
          </ul>

          <p>When you're ready:</p>
          <ul class="buttons">
            <li>
              <button class="start" v-on:click="startSemiphemeral">Start Semiphemeral</button>
              or
            </li>
            <li>
              <button
                class="download"
                v-on:click="downloadHistory"
              >Download my Twitter history again</button>
            </li>
          </ul>
        </div>

        <div v-if="state == 'C'">
          <p>
            Semiphemeral is
            <strong>active</strong>.
            <button class="pause" v-on:click="pauseSemiphemeral">Pause Semiphemeral</button>
          </p>
          <p v-if="!settingDeleteTweets && !settingRetweetsLikes" class="warning">
            Warning: Your settings are configured to not delete any tweets, retweets, or likes. Go
            <router-link to="/settings">change your settings</router-link>&nbsp;if you want Semiphemeral to delete your old tweets.
          </p>
        </div>

        <h2 v-if="activeJobs.length > 0 || pendingJobs.length > 0">Current status</h2>
        <ul v-if="activeJobs.length > 0" class="jobs">
          <li v-for="job in activeJobs">
            <Job v-bind:job="job"></Job>
          </li>
        </ul>
        <ul v-if="pendingJobs.length > 0" class="jobs">
          <li v-for="job in pendingJobs">
            <Job v-bind:job="job"></Job>
          </li>
        </ul>

        <h2 v-if="finishedJobs.length > 0">Log</h2>
        <ul v-if="finishedJobs.length > 0" class="jobs">
          <li v-for="job in finishedJobs">
            <Job v-bind:job="job"></Job>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script>
import Job from "./Dashboard/Job.vue";

export default {
  props: ["userScreenName"],
  data: function() {
    return {
      loading: false,
      activeJobs: [],
      pendingJobs: [],
      finishedJobs: [],
      settingPaused: null,
      settingFollowing: null,
      settingBlocked: null,
      settingDeleteTweets: null,
      settingRetweetsLikes: null
    };
  },
  computed: {
    state: function() {
      // There are 3 states:
      // A: paused, with pending or active jobs (fetching)
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
    mostRecentFetchFinished: function() {
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
    }
  },
  created: function() {
    this.fetchJobs();
  },
  methods: {
    postDashboard: function(action) {
      var that = this;
      this.loading = true;
      fetch("/api/dashboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action })
      })
        .then(function(response) {
          that.fetchJobs();
        })
        .catch(function(err) {
          console.log("Error", err);
          that.loading = false;
        });
    },
    startSemiphemeral: function() {
      this.postDashboard("start");
    },
    pauseSemiphemeral: function() {
      this.postDashboard("pause");
    },
    downloadHistory: function() {
      this.postDashboard("fetch");
    },
    reactivateAccount: function() {
      var that = this;
      this.loading = true;
      fetch("/api/dashboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "reactivate" })
      })
        .then(function(response) {
          if (response.status !== 200) {
            console.log("Error reactivating, status code: " + response.status);
            that.loading = false;
            return;
          }
          response.json().then(function(data) {
            console.log(data);
            that.loading = false;
            if (!data["unblocked"]) {
              alert("Nope, you're still blocked");
            } else {
              that.fetchJobs();
            }
          });
        })
        .catch(function(err) {
          console.log("Error", err);
          that.loading = false;
        });
    },
    fetchJobs: function() {
      var that = this;
      this.loading = true;

      // Get list of pending and active jobs
      fetch("/api/dashboard")
        .then(function(response) {
          if (response.status !== 200) {
            console.log("Error fetching jobs, status code: " + response.status);
            that.loading = false;
            return;
          }
          response.json().then(function(data) {
            that.loading = false;
            if (data["active_jobs"]) that.activeJobs = data["active_jobs"];
            else that.activeJobs = [];

            if (data["pending_jobs"]) that.pendingJobs = data["pending_jobs"];
            else that.pendingJobs = [];

            if (data["finished_jobs"])
              that.finishedJobs = data["finished_jobs"];
            else that.finishedJobs = [];

            that.settingPaused = data["setting_paused"];
            that.settingFollowing = data["setting_following"];
            that.settingBlocked = data["setting_blocked"];
            that.settingDeleteTweets = data["setting_delete_tweets"];
            that.settingRetweetsLikes = data["setting_retweet_likes"];
          });
        })
        .catch(function(err) {
          console.log("Error fetching jobs", err);
          that.loading = false;
        });
    }
  },
  components: {
    Job: Job
  }
};
</script>