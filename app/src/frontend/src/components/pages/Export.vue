<style scoped>
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
      <p>Export a spreadsheet and screenshots of your tweets. You can only do this once every 48 hours.</p>
    </template>
  </div>
</template>

<script>
export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      activeExportJobs: [],
      pendingExportJobs: [],
      finishedExportJobs: [],
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
            if (data["active_export_jobs"])
              that.activeExportJobs = data["active_export_jobs"];
            else that.activeExportJobs = [];

            if (data["pending_export_jobs"])
              that.pendingJobs = data["pending_export_jobs"];
            else that.pendingExportJobs = [];

            if (data["finished_export_jobs"])
              that.finishedExportJobs = data["finished_export_jobs"];
            else that.finishedExportJobs = [];
          });
        })
        .catch(function (err) {
          console.log("Error fetching export jobs", err);
          that.loading = false;
        });
    },
  },
};
</script>