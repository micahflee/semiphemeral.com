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
      <p>Export a spreadsheet and screenshots of your tweets. Make Semiphemeral has recently downloaded your tweets before starting an export. You can only do this once every 48 hours.</p>

      <template v-if="status == null || status == 'finished'">
        <p v-if="finishedTimestamp != null">
          Last export on
          <em>{{ humanReadableTimestamp(finishedTimestamp) }}</em>
          <button v-on:click="downloadExport">Download</button>
          <button v-on:click="deleteExport">Delete</button>
        </p>

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
        >Your export is getting created. You'll receive a direct message when it's ready to download.</p>
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
    downloadExport: function () {},
    deleteExport: function () {},
    humanReadableTimestamp: function (timestamp) {
      var date = new Date(timestamp * 1000);
      return date.toLocaleDateString() + " at " + date.toLocaleTimeString();
    },
  },
};
</script>