<script setup>
const props = defineProps({
  user: Object
})

function impersonate() {
  fetch("/admin_api/users/impersonate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      twitter_id: props.user.twitter_id
    })
  })
    .then(function (response) {
      window.location.href = "/dashboard"
    })
    .catch(function (err) {
      console.log("Error", err)
    })
}

function info() {
  window.location.href = "/admin_api/users/" + props.user.id
}
</script>

<template>
  <div>
    <a :href="`https://twitter.com/${user['twitter_screen_name']}`">{{ user['twitter_screen_name'] }}</a>
    <span>
      <button v-on:click="impersonate">impersonate</button>
    </span>
    <span v-if="user.blocked">
      <button v-on:click="info">info</button>
    </span>
  </div>
</template>

<style scoped>
button {
  margin: 0 0 0 10px;
  padding: 2px 5px;
  border: 1px solid #aeaeae;
  border-radius: 4px;
  font-size: 0.8em;
}
</style>