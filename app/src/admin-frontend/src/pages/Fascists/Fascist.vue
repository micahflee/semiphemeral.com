<script setup>
const props = defineProps({
  fascist: Object
})

const emit = defineEmits(["reload"])

function deleteFascist() {
  fetch("/admin_api/fascists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "delete",
      username: props['fascist']["username"]
    })
  })
    .then(function (response) {
      emit("reload");
    })
    .catch(function (err) {
      console.log("Error", err);
    })
}
</script>

<template>
  <div>
    <button class="delete" v-on:click="deleteFascist">Delete</button>
    <span class="username">
      <a :href="`https://twitter.com/${fascist['username']}`" target="_blank">{{ fascist['username'] }}</a>
    </span>
    <span class="comment">{{ fascist['comment'] }}</span>
  </div>
</template>

<style scoped>
button {
  font-size: 0.7em;
  padding: 0;
  margin-right: 1em;
}

.username {
  margin-right: 1em;
}

.comment {
  font-size: 0.8em;
  color: #999;
}
</style>