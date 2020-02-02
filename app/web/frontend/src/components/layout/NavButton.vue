<template>
  <button v-on:click="$emit('select-page')" v-bind:class="{ active: isActive }">{{ buttonText }}</button>
</template>

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