<template>
  <div v-bind:class="job.status">
    <template v-if="job.job_type == 'fetch'">
      <template v-if="job.status == 'pending'">
        <p
          class="status"
          v-if="scheduledTimestampInThePast"
        >Waiting to download all of your tweets and likes as soon as it's your turn in the queue</p>
        <p class="status" v-else>
          Waiting to download all of your tweets and likes, scheduled for
          <em>{{ humanReadableScheduledTimestamp }}</em>
        </p>
      </template>
      <template v-else>
        <p class="status">{{ progressStatus }}</p>
        <div>
          <span class="label">Tweets</span>
          <progress
            v-bind:value="progressTweets"
            v-bind:max="progressTotalTweets"
            v-bind:title="progressTweetsTitle"
          ></progress>
        </div>
        <div>
          <span class="label">Likes</span>
          <progress
            v-bind:value="progressLikes"
            v-bind:max="progressTotalLikes"
            v-bind:title="progressLikesTitle"
          ></progress>
        </div>
      </template>
    </template>

    <template v-if="job.job_type == 'delete'">
      <template v-if="job.status == 'pending'">
        <p
          class="progress-text"
          v-if="scheduledTimestampInThePast"
        >Waiting to delete your old tweets and likes as soon as it's your turn in the queue.</p>
        <p class="progress-text" v-else>
          Waiting to delete your old tweets and likes, scheduled for
          <em>{{ humanReadableScheduledTimestamp }}</em>.
        </p>
      </template>
      <template v-else>
        <p class="progress-text">
          Deleting your tweets and likes. Progress:
          <span class="progress">{{ job.progress }}</span>
        </p>
      </template>
    </template>
  </div>
</template>

<style scoped>
.label {
  display: inline-block;
  width: 60px;
  text-align: right;
  font-size: 11px;
  font-weight: bold;
}

progress {
  min-width: 200px;
}

.status {
  color: #666666;
  font-size: 12px;
}
</style>

<script>
export default {
  props: ["job"],
  computed: {
    progressTweets: function() {
      return JSON.parse(this.job.progress).tweets;
    },
    progressTotalTweets: function() {
      return JSON.parse(this.job.progress).total_tweets;
    },
    progressTweetsTitle: function() {
      return (
        "" + this.progressTweets + " / " + this.progressTotalTweets + " tweets"
      );
    },
    progressLikes: function() {
      return JSON.parse(this.job.progress).likes;
    },
    progressTotalLikes: function() {
      return JSON.parse(this.job.progress).total_likes;
    },
    progressLikesTitle: function() {
      return (
        "" + this.progressLikes + " / " + this.progressTotalLikes + " likes"
      );
    },
    progressStatus: function() {
      return JSON.parse(this.job.progress).status;
    },
    scheduledTimestampInThePast: function() {
      scheduleTimestamp = Math.floor(this.job["scheduled_timestamp"] * 1000);
      nowTimestamp = Date.now();
      return scheduleTimestamp <= nowTimestamp;
    },
    humanReadableScheduledTimestamp: function() {
      var date = new Date(this.job["scheduled_timestamp"] * 1000);
      return date.toLocaleDateString() + " at " + date.toLocaleTimeString();
    }
  }
};
</script>