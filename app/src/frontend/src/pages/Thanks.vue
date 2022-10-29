<script setup>
import { ref } from "vue"

const props = defineProps({
  userScreenName: String
})

const receipt_url = ref(null)
</script>

<template>
  <div>
    <h1>Thanks for the tip, @{{ userScreenName }}</h1>
    <p>
      <img src="/images/logo.png" />
    </p>
    <p>I'm glad you find this service useful!</p>
    <p v-if="receipt_url">
      <a :href="receipt_url" target="_blank">Click here</a> for your
      receipt.
    </p>
  </div>
</template>

<style scoped>
img {
  width: 200px;
  height: 200px;
}
</style>