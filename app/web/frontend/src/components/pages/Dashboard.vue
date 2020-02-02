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
      <div v-if="paused">
        <p>
          Semiphemeral is
          <strong>paused</strong>. Before starting Semiphemeral:
        </p>
        <ol>
          <li>
            Make sure your
            <button v-on:click="$emit('select-page', 'settings')">settings</button>
            are exactly as you want them
          </li>
          <li>
            Make sure you have manually chosen which of your old
            <button
              v-on:click="$emit('select-page', 'tweets')"
            >tweets</button>
            you want to make sure don't get automatically deleted
          </li>
        </ol>
        <p v-if="pendingJobs.length == 0 && activeJobs.length == 0">
          <button v-on:click="startSemiphemeral">Start Semiphemeral</button>
        </p>
        <p v-else>
          <em>
            You must wait for Semiphemeral to finish download all your old tweets
            before you can start deleting, so you don't accidentally delete tweets
            you wished you had kept.
          </em>
        </p>
      </div>

      <div v-if="!paused">
        <p>
          Semiphemeral is
          <strong>active</strong>.
          <button v-on:click="pauseSemiphemeral">Pause Semiphemeral</button>
        </p>
      </div>

      <h2>Current status</h2>

      <template v-if="activeJobs.length > 0">
        <ul class="jobs" v-for="job in activeJobs">
          <Job v-bind:job="job"></Job>
        </ul>
      </template>

      <template v-if="pendingJobs.length > 0">
        <ul class="jobs" v-for="job in pendingJobs">
          <Job v-bind:job="job"></Job>
        </ul>
      </template>
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
      pendingJobs: []
    };
  },
  created: function() {
    this.fetchJobs();
  },
  methods: {
    startSemiphemeral: function() {
      var that = this;
      this.loading = true;
      fetch("/api/dashboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "start" })
      })
        .then(function(response) {
          that.fetchJobs();
        })
        .catch(function(err) {
          console.log("Error starting semiphemeral", err);
          that.loading = false;
        });
    },
    pauseSemiphemeral: function() {
      var that = this;
      this.loading = true;
      fetch("/api/dashboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "pause" })
      })
        .then(function(response) {
          that.fetchJobs();
        })
        .catch(function(err) {
          console.log("Error pausing semiphemeral", err);
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