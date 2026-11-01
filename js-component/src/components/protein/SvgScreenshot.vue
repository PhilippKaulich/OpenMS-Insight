<template>
  <v-btn variant="text" size="large" icon="mdi-download" @click="triggerDownload">
    <v-icon>mdi-download</v-icon>
    <v-tooltip text="Save as SVG" location="bottom" activator="parent"></v-tooltip>
  </v-btn>
  <a ref="downloadLink" style="visibility: hidden;"></a>
  <v-dialog v-model="svgDownloadTriggered" persistent width="auto">
    <v-card :color="color">
      <v-card-text>
        Please stand by
        <v-progress-linear indeterminate color="white" class="mb-0"></v-progress-linear>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import domtoimage from 'dom-to-image-more'
import { useStreamlitDataStore } from '@/stores/streamlit-data'

export default defineComponent({
  name: 'SvgScreenshot',
  props: {
    elementId: {
      type: String,
      required: true
    },
    filename: {
      type: String,
      required: false,
      default: 'sequence'
    },
    color: {
      type: String,
      default: 'primary'
    }
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    return { streamlitDataStore }
  },
  data() {
    return {
      svgDownloadTriggered: false as boolean
    }
  },
  watch: {
    svgDownloadTriggered(value) {
      if (value) setTimeout(this.downloadSvg, 200)
    }
  },
  methods: {
    triggerDownload() {
      this.svgDownloadTriggered = true
    },
    async downloadSvg() {
      const elementToScreenshot = document.getElementById(this.elementId)
      if (elementToScreenshot) {
        await domtoimage.toSvg(elementToScreenshot, {
          filter(element: HTMLElement) {
            return (element.tagName !== 'BUTTON');
          },
          bgcolor: this.streamlitDataStore.theme?.backgroundColor ?? '#fff'
        }).then((dataUrl: string) => {
          const element = this.$refs.downloadLink as HTMLAnchorElement
          element.download = `${this.filename || 'sequence'}.svg`
          element.href = dataUrl
          element.click()
        }).finally(() => {
          this.svgDownloadTriggered = false
        })
      } else {
        this.svgDownloadTriggered = false
      }
    }
  },
})
</script>
