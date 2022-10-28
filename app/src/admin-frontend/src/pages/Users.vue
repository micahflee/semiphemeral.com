<script setup>
import { ref } from "vue"
import User from "./Users/User.vue";

const props = defineProps({
  userScreenName: String
})

const loading = ref(false)
const impersonatingTwitterUsername = ref(null)
const activeUsers = ref([])
const pausedUsers = ref([])
const blockedUsers = ref([])

const impersonatingLink = "https://twitter.com/" + impersonatingTwitterUsername.value

function fetchUsers() {
  loading.value = true

  // Get lists of users
  fetch("/admin_api/users")
    .then(function (response) {
      if (response.status !== 200) {
        console.log(
          "Error fetching users, status code: " + response.status
        )
        loading.value = false
        return
      }
      response.json().then(function (data) {
        loading.value = false
        impersonatingTwitterUsername.value = data["impersonating_twitter_username"]

        if (data["active_users"]) {
          activeUsers.value = data["active_users"]
        } else {
          activeUsers.value = []
        }

        if (data["paused_users"]) {
          pausedUsers.value = data["paused_users"]
        } else {
          pausedUsers.value = []
        }

        if (data["blocked_users"]) {
          blockedUsers.value = data["blocked_users"]
        } else {
          blockedUsers.value = []
        }
      })
    })
    .catch(function (err) {
      console.log("Error fetching users", err)
      loading.value = false
    })
}

function stopImpersonating() {
  loading.value = true

  fetch("/admin_api/users/impersonate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      twitter_id: "0",
    }),
  })
    .then(function (response) {
      fetchUsers()
    })
    .catch(function (err) {
      console.log("Error", err)
    })
}

fetchUsers()
</script>

<template>
  <div>
    <h1>Users</h1>

    <template v-if="impersonatingTwitterUsername != null">
      <p>
        You are impersonating twitter user
        <a target="_blank" v-bind:href="impersonatingLink">@{{ impersonatingTwitterUsername }}</a>.
        <button v-on:click="stopImpersonating">Stop impersonating.</button>
      </p>
    </template>

    <div v-if="activeUsers.length > 0" class="column">
      <h2>{{ activeUsers.length }} active users</h2>
      <ul>
        <li v-for="(user, index) in activeUsers" v-bind:key="index">
          <User v-bind:user="user"></User>
        </li>
      </ul>
    </div>

    <div v-if="pausedUsers.length > 0" class="column">
      <h2>{{ pausedUsers.length }} paused users</h2>
      <ul>
        <li v-for="(user, index) in pausedUsers" v-bind:key="index">
          <User v-bind:user="user"></User>
        </li>
      </ul>
    </div>

    <div v-if="blockedUsers.length > 0" class="column">
      <h2>{{ blockedUsers.length }} blocked users</h2>
      <ul>
        <li v-for="(user, index) in blockedUsers" v-bind:key="index">
          <User v-bind:user="user"></User>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.column {
  display: inline-block;
  vertical-align: top;
}
</style>
