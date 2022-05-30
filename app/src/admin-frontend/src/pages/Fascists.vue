<script setup>
import { ref } from "vue"
import Fascist from "./Fascists/Fascist.vue";

const props = defineProps({
  userScreenName: String
})

const loading = ref(false)
const fascists = ref([])

function onCreateSubmit() {
  loading.value = true;
  fetch("/admin_api/fascists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "create",
      username: $refs.username.value,
      comment: $refs.comment.value,
    }),
  })
    .then(function (response) {
      fetchFascists()
    })
    .catch(function (err) {
      console.log("Error", err)
      loading.value = false
    })
}

function fetchFascists() {
  loading.value = true;

  // Get lists of users
  fetch("/admin_api/fascists")
    .then(function (response) {
      if (response.status !== 200) {
        console.log(
          "Error fetching fascists, status code: " + response.status
        );
        loading.value = false
        return
      }
      response.json().then(function (data) {
        loading.value = false
        if (data["fascists"]) {
          fascists.value = data["fascists"]
        } else {
          fascists.value = []
        }
      })
    })
    .catch(function (err) {
      console.log("Error fetching users", err)
      loading.value = false
    })
}

fetchFascists()
</script>

<template>
  <div>
    <h1>Fascists</h1>
    <template v-if="loading">
      <p>
        <img src="/static/img/loading.gif" alt="Loading" />
      </p>
    </template>
    <template v-else>
      <form v-on:submit.prevent="onCreateSubmit">
        <fieldset>
          <legend>Add fascist</legend>
          <p>
            <label for="username">Username</label>
            <input
              type="text"
              placeholder="TuckerCarlson"
              name="username"
              ref="username"
            />
          </p>
          <p>
            <label for="comment">Comment</label>
            <input
              type="text"
              placeholder="US white nationalist propagandist"
              name="comment"
              ref="comment"
            />
          </p>
          <p>
            <input v-bind:disabled="loading" type="submit" value="Add" />
          </p>
        </fieldset>
      </form>

      <ul>
        <li v-for="(fascist, index) in fascists" v-bind:key="index">
          <Fascist
            v-bind:fascist="fascist"
            v-on:reload="fetchFascists()"
          ></Fascist>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
label {
  display: inline-block;
  width: 100px;
  text-align: right;
  margin-right: 10px;
}

input[type="text"] {
  width: 300px;
}

ul {
  padding: 0;
  list-style: none;
}
</style>