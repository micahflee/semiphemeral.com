<style scoped>
.label {
  display: inline-block;
  width: 60px;
  text-align: right;
  font-size: 11px;
  font-weight: bold;
}

.status {
  color: #666666;
  font-size: 12px;
}

.active p.progress {
  display: inline-block;
  border: 1px solid #5d8fad;
  padding: 10px;
  margin: 0;
  border-radius: 10px;
  background-color: #dbf2ff;
}

.finished .finished-timestamp {
  margin-right: 0.5em;
  display: inline-block;
  font-size: 0.8em;
  color: #666666;
}

.finished .progress {
  font-size: 0.8em;
}
</style>

<template>
  <div v-bind:class="job.status">
    <template v-if="job.job_type == 'fetch'">
      <template v-if="job.status == 'pending'">
        <p class="status" v-if="scheduledTimestampInThePast">
          Waiting to download all of your tweets and likes as soon as it's your
          turn in the queue
        </p>
        <p class="status" v-else>
          Waiting to download all of your tweets and likes, scheduled for
          <em>{{ humanReadableScheduledTimestamp }}</em>
        </p>
      </template>
      <template v-else-if="job.status == 'active'">
        <p class="status">{{ progressStatus }}</p>
        <p class="progress">
          Started downloading on
          <em>{{ humanReadableStartedTimestamp }}</em>
          <br />Downloaded <strong>{{ progressTweetsFetched }} tweets</strong>,
          <strong>{{ progressLikesFetched }} likes</strong> since then
        </p>
      </template>
      <template v-else-if="job.status == 'finished'">
        <p class="finished">
          <span class="finished-timestamp">{{
            humanReadableFinishedTimestamp
          }}</span>
          <span class="progress"
            >Downloaded {{ progressTweetsFetched }} tweets,
            {{ progressLikesFetched }} likes</span
          >
        </p>
      </template>
    </template>

    <template v-if="job.job_type == 'delete'">
      <template v-if="job.status == 'pending'">
        <p class="status" v-if="scheduledTimestampInThePast">
          Waiting to delete your old tweets, likes, and/or direct messages as
          soon as it's your turn in the queue
        </p>
        <p class="status" v-else>
          Waiting to delete your old tweets, likes, and/or direct messages,
          scheduled for
          <em>{{ humanReadableScheduledTimestamp }}</em>
        </p>
      </template>
      <template v-else-if="job.status == 'active'">
        <p class="status">{{ progressStatus }}</p>
        <p class="progress">
          Started deleting on
          <em>{{ humanReadableStartedTimestamp }}</em>
          <br />Downloaded <strong>{{ progressTweetsFetched }} tweets</strong>,
          <strong>{{ progressLikesFetched }} likes</strong>
          <br />Deleted <strong>{{ progressTweetsDeleted }} tweets</strong>,
          <strong>{{ progressRetweetsDeleted }} retweets</strong>,
          <strong>{{ progressLikesDeleted }} likes</strong>,
          <strong>{{ progressDMsDeleted }} direct messages</strong>
        </p>
      </template>
      <template v-else-if="job.status == 'finished'">
        <p class="finished">
          <span class="finished-timestamp">{{
            humanReadableFinishedTimestamp
          }}</span>
          <span class="progress">
            Downloaded {{ progressTweetsFetched }} tweets,
            {{ progressLikesFetched }} likes and deleted
            {{ progressTweetsDeleted }} tweets,
            {{ progressRetweetsDeleted }} retweets,
            {{ progressLikesDeleted }} likes
            <span v-if="progressDMsDeleted != ''"
              >and {{ progressDMsDeleted }} direct messages</span
            >
          </span>
        </p>
      </template>
    </template>

    <template v-if="job.job_type == 'delete_dms'">
      <template v-if="job.status == 'pending'">
        <p class="status" v-if="scheduledTimestampInThePast">
          Waiting to delete all of your old direct messages as soon as it's your
          turn in the queue
        </p>
        <p class="status" v-else>
          Waiting to delete all of your old direct messages, scheduled for
          <em>{{ humanReadableScheduledTimestamp }}</em>
        </p>
      </template>
      <template v-else-if="job.status == 'active'">
        <p class="status">{{ progressStatus }}</p>
        <p class="progress">
          Started deleting old direct messages on
          <em>{{ humanReadableStartedTimestamp }}</em>
          <br />Deleted
          <strong>{{ progressDMsDeleted }} direct messages</strong>, skipped
          <strong>{{ progressDMsSkipped }} direct messages</strong>
        </p>
      </template>
      <template v-else-if="job.status == 'finished'">
        <p class="finished">
          <span class="finished-timestamp">{{
            humanReadableFinishedTimestamp
          }}</span>
          <span class="progress"
            >Deleted {{ progressDMsDeleted }} direct messages (skipped
            {{ progressDMsSkipped }})</span
          >
        </p>
      </template>
    </template>

    <template v-if="job.job_type == 'delete_dm_groups'">
      <template v-if="job.status == 'pending'">
        <p class="status" v-if="scheduledTimestampInThePast">
          Waiting to delete all of your old group direct messages as soon as
          it's your turn in the queue
        </p>
        <p class="status" v-else>
          Waiting to delete all of your old group direct messages, scheduled for
          <em>{{ humanReadableScheduledTimestamp }}</em>
        </p>
      </template>
      <template v-else-if="job.status == 'active'">
        <p class="status">{{ progressStatus }}</p>
        <p class="progress">
          Started deleting old group direct messages on
          <em>{{ humanReadableStartedTimestamp }}</em>
          <br />Deleted
          <strong>{{ progressDMsDeleted }} direct messages</strong>
          (skipped {{ progressDMsSkipped }})
        </p>
      </template>
      <template v-else-if="job.status == 'finished'">
        <p class="finished">
          <span class="finished-timestamp">{{
            humanReadableFinishedTimestamp
          }}</span>
          <span class="progress"
            >Deleted {{ progressDMsDeleted }} group direct messages (skipped
            {{ progressDMsSkipped }})</span
          >
        </p>
      </template>
    </template>
  </div>
</template>

<script>
export default {
  props: ["job"],
  computed: {
    progressTweetsFetched: function () {
      return this.getProgressVal(this.job.data, "tweets_fetched");
    },
    progressLikesFetched: function () {
      return this.getProgressVal(this.job.data, "likes_fetched");
    },
    progressTweetsDeleted: function () {
      return this.getProgressVal(this.job.data, "tweets_deleted");
    },
    progressRetweetsDeleted: function () {
      return this.getProgressVal(this.job.data, "retweets_deleted");
    },
    progressLikesDeleted: function () {
      return this.getProgressVal(this.job.data, "likes_deleted");
    },
    progressDMsDeleted: function () {
      return this.getProgressVal(this.job.data, "dms_deleted");
    },
    progressDMsSkipped: function () {
      return this.getProgressVal(this.job.data, "dms_skipped");
    },
    progressStatus: function () {
      return this.getProgressVal(this.job.data, "status");
    },
    scheduledTimestampInThePast: function () {
      var scheduledTimestamp = Math.floor(
        this.job["scheduled_timestamp"] * 1000
      );
      var nowTimestamp = Date.now();
      return scheduledTimestamp <= nowTimestamp;
    },
    humanReadableScheduledTimestamp: function () {
      return this.humanReadableTimestamp(this.job["scheduled_timestamp"]);
    },
    humanReadableStartedTimestamp: function () {
      return this.humanReadableTimestamp(this.job["started_timestamp"]);
    },
    humanReadableFinishedTimestamp: function () {
      return this.humanReadableTimestamp(this.job["finished_timestamp"]);
    },
  },
  methods: {
    humanReadableTimestamp: function (timestamp) {
      var date = new Date(timestamp * 1000);
      return date.toLocaleDateString() + " at " + date.toLocaleTimeString();
    },
    getProgressVal: function (data, key) {
      var p = JSON.parse(data);
      if (p) {
        return p["progress"][key];
      } else {
        return "";
      }
    },
  },
};
</script>