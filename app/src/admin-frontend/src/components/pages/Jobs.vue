<style scoped>
ul {
  list-style: none;
  padding: 0;
}

li .job-id {
  display: inline-block;
  vertical-align: middle;
  margin-right: 10px;
  width: 50px;
  font-size: 0.9em;
}

li .job-user {
  display: inline-block;
  vertical-align: middle;
  margin-right: 10px;
  width: 150px;
  font-size: 0.9em;
}

li .job-type {
  display: inline-block;
  vertical-align: middle;
  margin-right: 10px;
  width: 60px;
  font-size: 0.8em;
}

li .job-date {
  display: inline-block;
  vertical-align: middle;
  margin-right: 10px;
  width: 250px;
  font-size: 0.8em;
  color: #666666;
}

li .job-progress {
  display: block;
  font-size: 0.9em;
  font-family: monospace;
  color: #666;
  margin-left: 65px;
}
</style>

<template>
  <div>
    <h1>Jobs</h1>

    <div v-if="active_jobs.length > 0">
      <h2>{{ active_jobs.length }} active jobs</h2>
      <ul>
        <li v-for="job in active_jobs">
          <span class="job-id">{{ job.id }}</span>
          <span class="job-user" v-if="job.twitter_username != None">
            <a v-bind:href="job.twitter_link" target="_blank">{{
              job.twitter_username
            }}</a>
          </span>
          <span class="job-user" v-else>
            <p>unknown user</p>
          </span>
          <span class="job-type">{{ job.job_type }}</span>
          <span class="job-date"
            >started {{ formatJobDate(job.started_timestamp) }}</span
          >
          <span class="job-progress">{{ job.progress }}</span>
        </li>
      </ul>
    </div>

    <div v-if="pending_jobs.length > 0">
      <h2>{{ pending_jobs.length }} pending jobs</h2>
      <ul>
        <li v-for="job in pending_jobs">
          <span class="job-id">{{ job.id }}</span>
          <span class="job-user" v-if="job.twitter_username != None">
            <a v-bind:href="job.twitter_link" target="_blank">{{
              job.twitter_username
            }}</a>
          </span>
          <span class="job-user" v-else>
            <p>unknown user</p>
          </span>
          <span class="job-type">{{ job.job_type }}</span>
          <span class="job-date"
            >scheduled {{ formatJobDate(job.scheduled_timestamp) }}</span
          >
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      active_jobs: [],
      pending_jobs: [],
    };
  },
  created: function () {
    this.fetchJobs();
  },
  methods: {
    fetchJobs: function () {
      var that = this;
      this.loading = true;

      // Get lists of jobs
      fetch("/admin_api/jobs")
        .then(function (response) {
          if (response.status !== 200) {
            console.log("Error fetching tips, status code: " + response.status);
            that.loading = false;
            return;
          }
          response.json().then(function (data) {
            that.loading = false;
            that.active_jobs = data["active_jobs"];
            that.pending_jobs = data["pending_jobs"];
          });
        })
        .catch(function (err) {
          console.log("Error fetching jobs", err);
          that.loading = false;
        });
    },
    formatJobDate: function (timestamp) {
      var date = new Date(timestamp * 1000);
      var month_num = date.getMonth() + 1;
      var month = "";
      if (month_num == 1) {
        month = "January";
      } else if (month_num == 2) {
        month = "February";
      } else if (month_num == 3) {
        month = "March";
      } else if (month_num == 4) {
        month = "April";
      } else if (month_num == 5) {
        month = "May";
      } else if (month_num == 6) {
        month = "June";
      } else if (month_num == 7) {
        month = "July";
      } else if (month_num == 8) {
        month = "August";
      } else if (month_num == 9) {
        month = "September";
      } else if (month_num == 10) {
        month = "October";
      } else if (month_num == 11) {
        month = "November";
      } else if (month_num == 12) {
        month = "December";
      }
      return (
        month +
        " " +
        date.getDate() +
        ", " +
        date.getFullYear() +
        " " +
        date.getHours() +
        ":" +
        date.getMinutes()
      );
    },
  },
};
</script>
