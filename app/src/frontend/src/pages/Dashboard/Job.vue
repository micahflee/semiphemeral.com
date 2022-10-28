<script setup>
const props = defineProps(['job'])

function humanReadableTimestamp(timestamp) {
    if (timestamp == null) {
        return "null"
    }
    var date = new Date(timestamp * 1000)
    return date.toLocaleDateString() + " at " + date.toLocaleTimeString()
}

function getProgressVal(key) {
    try {
        var p = JSON.parse(props.job.data)
        if (p && p["progress"]) {
            return p["progress"][key]
        } else {
            return ""
        }
    } catch (error) {
        console.log("Error JSON parsing: " + props.job.data)
        return ""
    }
}

function scheduledTimestampInThePast() {
    var scheduledTimestamp = Math.floor(props.jobScheduledTimestamp.value * 1000)
    return scheduledTimestamp <= Date.now()
}
</script>

<template>
    <div v-bind:class="job.status">
        <template v-if="job.job_type == 'fetch'">
            <template v-if="job.status == 'pending'">
                <p class="status" v-if="scheduledTimestampInThePast()">
                    Waiting to download all of your tweets and likes as soon as it's your
                    turn in the queue
                </p>
                <p class="status" v-else>
                    Waiting to download all of your tweets and likes, scheduled for
                    <em>{{ humanReadableTimestamp(job.scheduled_timestamp) }}</em>
                </p>
            </template>
            <template v-else-if="job.status == 'active'">
                <p class="status">{{ getProgressVal("status") }}</p>
                <p class="progress">
                    Started downloading on
                    <em>{{ humanReadableTimestamp(job.started_timestamp) }}</em>
                    <br />Downloaded <strong>{{ getProgressVal("tweets_fetched") }} tweets</strong>,
                    <strong>{{ getProgressVal("likes_fetched") }} likes</strong> since then
                </p>
            </template>
            <template v-else-if="job.status == 'finished'">
                <p class="finished">
                    <span class="finished-timestamp">{{
                            humanReadableTimestamp(job.finished_timestamp)
                    }}</span>
                    <span class="progress">Downloaded {{ getProgressVal("tweets_fetched") }} tweets,
                        {{ getProgressVal("likes_fetched") }} likes</span>
                </p>
            </template>
        </template>

        <template v-if="job.job_type == 'delete'">
            <template v-if="job.status == 'pending'">
                <p class="status" v-if="scheduledTimestampInThePast()">
                    Waiting to delete your old tweets, likes, and/or direct messages as
                    soon as it's your turn in the queue
                </p>
                <p class="status" v-else>
                    Waiting to delete your old tweets, likes, and/or direct messages,
                    scheduled for
                    <em>{{ humanReadableTimestamp(job.scheduled_timestamp) }}</em>
                </p>
            </template>
            <template v-else-if="job.status == 'active'">
                <p class="status">{{ getProgressVal("status") }}</p>
                <p class="progress">
                    Started deleting on
                    <em>{{ humanReadableTimestamp(job.started_timestamp) }}</em>
                    <br />Downloaded <strong>{{ getProgressVal("tweets_fetched") }} tweets</strong>,
                    <strong>{{ getProgressVal("likes_fetched") }} likes</strong>
                    <br />Deleted <strong>{{ getProgressVal("tweets_deleted") }} tweets</strong>,
                    <strong>{{ getProgressVal("retweets_deleted") }} retweets</strong>,
                    <strong>{{ getProgressVal("likes_deleted") }} likes</strong>,
                    <strong>{{ getProgressVal("dms_deleted") }} direct messages</strong>
                </p>
            </template>
            <template v-else-if="job.status == 'finished'">
                <p class="finished">
                    <span class="finished-timestamp">{{
                            humanReadableTimestamp(job.finished_timestamp)
                    }}</span>
                    <span class="progress">
                        Downloaded {{ getProgressVal("tweets_fetched") }} tweets,
                        {{ getProgressVal("likes_fetched") }} likes and deleted
                        {{ getProgressVal("tweets_deleted") }} tweets,
                        {{ getProgressVal("retweets_deleted") }} retweets,
                        {{ getProgressVal("likes_deleted") }} likes
                        <span v-if="getProgressVal('dms_deleted') != ''">
                            and {{ getProgressVal("dms_deleted") }} direct
                            messages</span>
                    </span>
                </p>
            </template>
        </template>

        <template v-if="job.job_type == 'delete_dms'">
            <template v-if="job.status == 'pending'">
                <p class="status" v-if="scheduledTimestampInThePast()">
                    Waiting to delete all of your old direct messages as soon as it's your
                    turn in the queue
                </p>
                <p class="status" v-else>
                    Waiting to delete all of your old direct messages, scheduled for
                    <em>{{ humanReadableTimestamp(job.scheduled_timestamp) }}</em>
                </p>
            </template>
            <template v-else-if="job.status == 'active'">
                <p class="status">{{ getProgressVal("status") }}</p>
                <p class="progress">
                    Started deleting old direct messages on
                    <em>{{ humanReadableTimestamp(job.started_timestamp) }}</em>
                    <br />Deleted
                    <strong>{{ getProgressVal("dms_deleted") }} direct messages</strong>, skipped
                    <strong>{{ getProgressVal("dms_skipped") }} direct messages</strong>
                </p>
            </template>
            <template v-else-if="job.status == 'finished'">
                <p class="finished">
                    <span class="finished-timestamp">{{
                            humanReadableTimestamp(job.finished_timestamp)
                    }}</span>
                    <span class="progress">Deleted {{ getProgressVal("dms_deleted") }} direct messages (skipped
                        {{ getProgressVal("dms_skipped") }})</span>
                </p>
            </template>
        </template>

        <template v-if="job.job_type == 'delete_dm_groups'">
            <template v-if="job.status == 'pending'">
                <p class="status" v-if="scheduledTimestampInThePast()">
                    Waiting to delete all of your old group direct messages as soon as
                    it's your turn in the queue
                </p>
                <p class="status" v-else>
                    Waiting to delete all of your old group direct messages, scheduled for
                    <em>{{ humanReadableTimestamp(job.scheduled_timestamp) }}</em>
                </p>
            </template>
            <template v-else-if="job.status == 'active'">
                <p class="status">{{ getProgressVal("status") }}</p>
                <p class="progress">
                    Started deleting old group direct messages on
                    <em>{{ humanReadableTimestamp(job.started_timestamp) }}</em>
                    <br />Deleted
                    <strong>{{ getProgressVal("dms_deleted") }} direct messages</strong>
                    (skipped {{ getProgressVal("dms_skipped") }})
                </p>
            </template>
            <template v-else-if="job.status == 'finished'">
                <p class="finished">
                    <span class="finished-timestamp">{{
                            humanReadableTimestamp(job.finished_timestamp)
                    }}</span>
                    <span class="progress">Deleted {{ getProgressVal("dms_deleted") }} group direct messages (skipped
                        {{ getProgressVal("dms_skipped") }})</span>
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
    font-size: 0.9em;
    color: #999999;
}

.finished .progress {
    font-size: 0.9em;
    color: #000000;
}
</style>