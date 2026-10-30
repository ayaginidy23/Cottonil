// =============================================================================
// image.js - Shrink a photo in the browser before uploading it
// -----------------------------------------------------------------------------
// Phone photos are often 4-8 MB. The model only needs ~1000 px to recognise a
// garment, so we redraw the photo on a canvas at max 1024 px as JPEG (~150 KB):
// faster upload, cheaper request, and it removes EXIF data such as location.
// =============================================================================
export function resizeImage(file, maxSide = 1024, quality = 0.85) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith('image/')) {
      reject(new Error('Please choose an image file.'))
      return
    }
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale)
      canvas.height = Math.round(img.height * scale)
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      resolve(canvas.toDataURL('image/jpeg', quality))   // "data:image/jpeg;base64,..."
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Could not read this image.'))
    }
    img.src = url
  })
}