<template>
  <div class="modification-picker">
    <v-text-field
      v-model="query"
      autofocus
      clearable
      hide-details
      density="compact"
      variant="outlined"
      prepend-inner-icon="mdi-magnify"
      :placeholder="`Name or mass (${searchable.length} for ${site})`"
      @keydown.enter.prevent="pickFirst"
    />
    <v-list density="compact" class="modification-picker-list">
      <template v-if="query">
        <v-list-subheader>
          {{ matches.length === 0 ? 'No match' : `${matches.length} match${matches.length === 1 ? '' : 'es'}` }}
        </v-list-subheader>
        <v-list-item
          v-for="option in shownMatches"
          :key="option.value"
          :title="option.title"
          :active="option.value === selected"
          @click="$emit('pick', option.value)"
        />
        <v-list-item
          v-if="matches.length > shownMatches.length"
          disabled
          :title="`${matches.length - shownMatches.length} more, refine the search`"
        />
      </template>
      <template v-else>
        <template v-if="suggestions.length > 0">
          <v-list-subheader>Suggested for {{ site }}</v-list-subheader>
          <v-list-item
            v-for="option in suggestions"
            :key="option.value"
            :title="option.title"
            :active="option.value === selected"
            @click="$emit('pick', option.value)"
          />
          <v-divider />
        </template>
        <v-list-item
          v-if="selected"
          prepend-icon="mdi-close"
          title="None"
          @click="$emit('pick', 'None')"
        />
        <v-list-item prepend-icon="mdi-pencil" title="Custom mass" @click="$emit('pick', 'Custom')" />
      </template>
    </v-list>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import {
  searchOptions,
  suggestedOptions,
  type ModificationOption,
} from '@/components/sequence/modification'

// A searchable modification menu: suggestions for the site until a search
// is typed, then the library's matches
export default defineComponent({
  name: 'ModificationPicker',
  props: {
    site: { type: String, required: true },
    options: { type: Array as PropType<ModificationOption[]>, required: true },
    suggested: {
      type: Object as PropType<Record<string, string[]> | null>,
      default: null,
    },
    selected: { type: String as PropType<string | undefined>, default: undefined },
  },
  emits: ['pick'],
  data() {
    return { query: '' as string | null }
  },
  computed: {
    searchable(): ModificationOption[] {
      return this.options.filter((o) => o.mass !== null)
    },
    suggestions(): ModificationOption[] {
      return suggestedOptions(this.site, this.searchable, this.suggested)
    },
    matches(): ModificationOption[] {
      return searchOptions(this.searchable, this.query ?? '')
    },
    shownMatches(): ModificationOption[] {
      return this.matches.slice(0, 50)
    },
  },
  methods: {
    pickFirst(): void {
      const first = this.query ? this.matches[0] : undefined
      if (first) this.$emit('pick', first.value)
    },
  },
})
</script>

<style scoped>
.modification-picker {
  padding: 8px;
}
.modification-picker-list {
  max-height: 320px;
  overflow-y: auto;
}
</style>
