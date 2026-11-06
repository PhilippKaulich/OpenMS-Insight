<template>
  <v-btn variant="text" :size="size" icon="mdi-download" @click="triggerDownload">
    <v-icon>mdi-download</v-icon>
    <v-tooltip :text="title" location="bottom" activator="parent"></v-tooltip>
  </v-btn>
  <v-dialog v-model="downloadTriggered" persistent width="auto">
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
import { RASTER_SCALE, downloadTitle, encodeCanvas, imageFileName, imageFormatOf, saveImage } from '@/utils/imageExport'

/**
 * Download button saving a part of the page as an image: SVG (default), or
 * PNG, JPEG or WebP at RASTER_SCALE times its size on screen. Buttons inside
 * the part are left out.
 */
export default defineComponent({
  name: 'ImageScreenshot',
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
    /** 'svg', 'png', 'jpeg' or 'webp' (anything else: 'svg') */
    format: {
      type: String,
      required: false,
      default: 'svg'
    },
    color: {
      type: String,
      default: 'primary'
    },
    size: {
      type: String,
      default: 'large'
    }
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    return { streamlitDataStore }
  },
  data() {
    return {
      downloadTriggered: false as boolean
    }
  },
  computed: {
    title(): string {
      return downloadTitle(imageFormatOf(this.format))
    }
  },
  watch: {
    downloadTriggered(value) {
      if (value) setTimeout(this.download, 200)
    }
  },
  methods: {
    triggerDownload() {
      this.downloadTriggered = true
    },
    async download() {
      const elementToScreenshot = document.getElementById(this.elementId)
      if (!elementToScreenshot) {
        this.downloadTriggered = false
        return
      }
      const format = imageFormatOf(this.format)
      const options = {
        filter(element: HTMLElement) {
          return (element.tagName !== 'BUTTON');
        },
        bgcolor: this.streamlitDataStore.theme?.backgroundColor ?? '#fff'
      }
      const name = this.filename || 'sequence'
      try {
        if (format === 'svg') {
          saveImage(await domtoimage.toSvg(elementToScreenshot, options), imageFileName(name, 'svg'))
        } else {
          const canvas = await domtoimage.toCanvas(elementToScreenshot, { ...options, scale: RASTER_SCALE })
          const image = encodeCanvas(canvas, format)
          saveImage(image.url, imageFileName(name, image.format))
        }
      } finally {
        this.downloadTriggered = false
      }
    }
  },
})
</script>
