<style scoped>
.info {
  font-style: italic;
  color: #666666;
}

button {
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
</style>

<template>
  <div>
    <h1>Export your tweets</h1>

    <template v-if="loading">
      <p>
        <img src="/static/img/loading.gif" alt="Loading" />
      </p>
    </template>
    <template v-else>
      <p>This feature lets you export a spreadsheet of your tweets and retweets, and a screenshot of each of your tweets and retweets. Make sure that Semiphemeral has downloaded your latest tweets before starting an export. You can only export your tweets once every 48 hours.</p>

      <template v-if="status == null || status == 'finished'">
        <div v-if="finishedTimestamp != null">
          <p>
            <strong>
              Last export on
              <em>{{ humanReadableTimestamp(finishedTimestamp) }}</em>
            </strong>
          </p>
          <p v-if="downloadable">
            <button v-on:click="downloadExport">Download</button>
            <button v-on:click="deleteExport">Delete</button>
          </p>
          <p v-else>You have deleted this export from the server</p>
        </div>
        <p v-if="!tooSoon">
          <button v-on:click="startExport">Start Export</button>
        </p>
        <p v-else class="info">You can only export your tweets once every 48 hours.</p>
      </template>
      <template v-else>
        <p
          v-if="status == 'pending'"
          class="info"
        >Waiting to create your export as soon as it's your turn in the queue.</p>
        <p
          v-if="status == 'active'"
          class="info"
        >We're busy screenshotting all of your tweets. You'll receive a direct message when it's ready to download.</p>
      </template>
    </template>
  </div>
</template>

<script>
export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      status: null,
      finishedTimestamp: null,
      tooSoon: false,
      downloadable: false,
    };
  },
  created: function () {
    this.fetchExportJobs();
  },
  methods: {
    fetchExportJobs: function () {
      var that = this;
      this.loading = true;

      // Get list of pending, active, and finished export jobs
      fetch("/api/export")
        .then(function (response) {
          if (response.status !== 200) {
            console.log(
              "Error fetching export jobs, status code: " + response.status
            );
            that.loading = false;
            return;
          }
          response.json().then(function (data) {
            that.loading = false;
            that.status = data["status"];
            that.finishedTimestamp = data["finished_timestamp"];
            that.tooSoon = data["too_soon"];
            that.downloadable = data["downloadable"];
          });
        })
        .catch(function (err) {
          console.log("Error fetching export jobs", err);
          that.loading = false;
        });
    },
    startExport: function () {
      var that = this;
      this.loading = true;
      fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "start" }),
      })
        .then(function (response) {
          that.fetchExportJobs();
        })
        .catch(function (err) {
          console.log("Error", err);
          that.loading = false;
        });
    },
    downloadExport: function () {
      document.location = "/export/download";
    },
    deleteExport: function () {
      var that = this;
      this.loading = true;
      fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete" }),
      })
        .then(function (response) {
          that.fetchExportJobs();
        })
        .catch(function (err) {
          console.log("Error", err);
          that.loading = false;
        });
    },
    humanReadableTimestamp: function (timestamp) {
      var date = new Date(timestamp * 1000);
      return date.toLocaleDateString() + " at " + date.toLocaleTimeString();
    },
  },
};
</script>