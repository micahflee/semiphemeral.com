<style scoped>
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
}

ul.jobs {
  list-style: none;
  padding: 0;
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

        <p>
          When you're ready,
          <button class="start" v-on:click="startSemiphemeral">Start Semiphemeral</button>
          or
          <button
            class="download"
            v-on:click="downloadHistory"
          >Download my Twitter history again</button>
        </p>
      </div>

      <div v-if="state == 'C'">
        <p>
          Semiphemeral is
          <strong>active</strong>.
          <button v-on:click="pauseSemiphemeral">Pause Semiphemeral</button>
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
      paused: null,
      activeJobs: [],
      pendingJobs: [],
      finishedJobs: []
    };
  },
  computed: {
    state: function() {
      // There are 3 states:
      // A: paused, with pending or active jobs (fetching)
      // B: paused, with only finished or cancelled jobs
      // C: not paused
      // More info: https://github.com/micahflee/semiphemeral.com/issues/8
      if (this.paused) {
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

            that.paused = data["paused"];
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