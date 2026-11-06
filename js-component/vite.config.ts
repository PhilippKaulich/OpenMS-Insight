import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import license from 'rollup-plugin-license'
import { readFileSync } from 'node:fs'

const CSS_ONLY_PACKAGES = ['@mdi/font']

function readPackage(name: string) {
  const dir = fileURLToPath(new URL(`./node_modules/${name}/`, import.meta.url))
  const pkg = JSON.parse(readFileSync(`${dir}package.json`, 'utf8'))
  return {
    name: pkg.name,
    version: pkg.version,
    license: pkg.license,
    licenseText: readFileSync(`${dir}LICENSE`, 'utf8')
  }
}

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
    // The bundles keep only some of the license headers of the libraries they
    // contain, so write the license text of every bundled package next to them.
    license({
      thirdParty: {
        includePrivate: false,
        output: {
          file: fileURLToPath(new URL('./dist/THIRD-PARTY-LICENSES.txt', import.meta.url)),
          // Packages that reach the bundle only through a stylesheet (the
          // icon font) are not modules rollup sees, so they are added here.
          template(dependencies) {
            const entries = [...dependencies, ...CSS_ONLY_PACKAGES.map(readPackage)]
            return entries
              .map((dep) =>
                [
                  `Name: ${dep.name}`,
                  `Version: ${dep.version}`,
                  `License: ${dep.license}`,
                  '',
                  (dep.licenseText || '').trim()
                ].join('\n')
              )
              .join('\n\n---\n\n')
          }
        }
      }
    })
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  base: './',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    // One stylesheet for every view, as before the views became separate
    // chunks: some views rely on styles another view's component brings
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]'
      }
    }
  },
  server: {
    port: 5173,
    strictPort: true
  }
})
