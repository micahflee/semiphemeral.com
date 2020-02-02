<template>
  <button v-on:click="$emit('select-page')" v-bind:class="{ active: isActive }">{{ buttonText }}</button>
</template>

<style scoped>
button {
  border: 0;
  background-color: transparent;
  padding: 5px;
  cursor: pointer;
}

button.active {
  color: #42465d;
  border-bottom: 3px solid #42465d;
}
</style>

<script>
export default {
  props: ["currentPageComponent", "buttonText", "pageComponent"],
  computed: {
    isActive: function() {
      return this.currentPageComponent == this.pageComponent;
    }
  }
};
</script>