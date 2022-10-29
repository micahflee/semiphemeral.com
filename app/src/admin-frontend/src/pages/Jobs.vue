<script setup>
import { ref } from "vue"

const props = defineProps({
  userScreenName: String
})

const loading = ref(false)
const started_jobs = ref([])
const queued_jobs = ref([])
const scheduled_jobs = ref([])
const other_jobs = ref([])

function fetchJobs() {
  loading.value = true

  // Get lists of jobs
  fetch("/admin_api/jobs")
    .then(function (response) {
      if (response.status !== 200) {
        console.log("Error fetching tips, status code: " + response.status)
        loading.value = false
        return
      }
      response.json().then(function (data) {
        loading.value = false
        started_jobs.value = data["started_jobs"]
        queued_jobs.value = data["queued_jobs"]
        scheduled_jobs.value = data["scheduled_jobs"]
        other_jobs.value = data["other_jobs"]
      });
    })
    .catch(function (err) {
      console.log("Error fetching jobs", err)
      loading.value = false
    })
}

function addZero(i) {
  if (i < 10) {
    i = "0" + i
  }
  return i
}

function formatJobDate(timestamp) {
  var date = new Date(timestamp * 1000)
  var month_num = date.getMonth() + 1
  var month = ""
  if (month_num == 1) {
    month = "January"
  } else if (month_num == 2) {
    month = "February"
  } else if (month_num == 3) {
    month = "March"
  } else if (month_num == 4) {
    month = "April"
  } else if (month_num == 5) {
    month = "May"
  } else if (month_num == 6) {
    month = "June"
  } else if (month_num == 7) {
    month = "July"
  } else if (month_num == 8) {
    month = "August"
  } else if (month_num == 9) {
    month = "September"
  } else if (month_num == 10) {
    month = "October"
  } else if (month_num == 11) {
    month = "November"
  } else if (month_num == 12) {
    month = "December"
  }
  return (
    month +
    " " +
    date.getUTCDate() +
    ", " +
    date.getUTCFullYear() +
    " " +
    addZero(date.getUTCHours()) +
    ":" +
    addZero(date.getUTCMinutes())
  )
}

fetchJobs()
</script>

<template>
  <div>
    <h1>Jobs</h1>

    <div v-if="started_jobs.length > 0">
      <h2>{{ started_jobs.length }} started jobs</h2>
      <ul>
        <li v-for="(job, index) in started_jobs" v-bind:key="index">
          <span class="job-id">{{ job.id }}</span>
          <span class="job-user" v-if="job.twitter_username != null">
            <a v-bind:href="job.twitter_link" target="_blank">{{
                job.twitter_username
            }}</a>
          </span>
          <span class="job-user" v-else>
            <p>unknown user</p>
          </span>
          <span class="job-type">{{ job.job_type }}</span>
          <span class="job-date">started {{ formatJobDate(job.started_timestamp) }} UTC</span>
          <span class="job-data">{{ job.data }}</span>
        </li>
      </ul>
    </div>

    <div v-if="queued_jobs.length > 0">
      <h2>{{ queued_jobs.length }} queued jobs</h2>
      <ul>
        <li v-for="(job, index) in queued_jobs" v-bind:key="index">
          <span class="job-id">{{ job.id }}</span>
          <span class="job-user" v-if="job.twitter_username != null">
            <a v-bind:href="job.twitter_link" target="_blank">{{
                job.twitter_username
            }}</a>
          </span>
          <span class="job-user" v-else>
            <p>unknown user</p>
          </span>
          <span class="job-type">{{ job.job_type }}</span>
          <span class="job-data">{{ job.data }}</span>
        </li>
      </ul>
    </div>

    <div v-if="scheduled_jobs.length > 0">
      <h2>{{ scheduled_jobs.length }} scheduled jobs</h2>
      <ul>
        <li v-for="(job, index) in scheduled_jobs" v-bind:key="index">
          <span class="job-id">{{ job.id }}</span>
          <span class="job-user" v-if="job.twitter_username != null">
            <a v-bind:href="job.twitter_link" target="_blank">{{
                job.twitter_username
            }}</a>
          </span>
          <span class="job-user" v-else>
            <p>unknown user</p>
          </span>
          <span class="job-type">{{ job.job_type }}</span>
          <span class="job-date">scheduled {{ formatJobDate(job.scheduled_timestamp) }} UTC</span>
          <span class="job-data">{{ job.data }}</span>
        </li>
      </ul>
    </div>

    <div v-if="other_jobs.length > 0">
      <h2>{{ other_jobs.length }} other jobs</h2>
      <ul>
        <li v-for="(job, index) in other_jobs" v-bind:key="index">
          <span class="job-id">{{ job.id }}</span>
          <span class="job-user" v-if="job.twitter_username != null">
            <a v-bind:href="job.twitter_link" target="_blank">{{
                job.twitter_username
            }}</a>
          </span>
          <span class="job-user" v-else>
            <p>unknown user</p>
          </span>
          <span class="job-type">{{ job.job_type }}</span>
          <span class="job-date">scheduled {{ formatJobDate(job.scheduled_timestamp) }} UTC</span>
          <span class="job-date">started {{ formatJobDate(job.started_timestamp) }} UTC</span>
          <span class="job-data">redis: {{ job.redis_status }}</span>
          <span class="job-data">{{ job.data }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
ul {
  list-style: none;
  padding: 0;
}

li {
  white-space: nowrap;
}

li .job-id {
  display: inline-block;
  vertical-align: middle;
  margin-right: 10px;
  width: 60px;
  font-size: 0.9em;
}

li .job-container-name {
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

li .job-data {
  font-size: 0.9em;
  font-family: monospace;
  color: #666;
}
</style>