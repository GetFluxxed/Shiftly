const $ = (selector) => document.querySelector(selector);

const imageInput = $("#image-input");
const dropzone = $("#dropzone");
const dropzoneEmpty = $("#dropzone-empty");
const previewState = $("#preview-state");
const imagePreview = $("#image-preview");
const fileName = $("#file-name");
const notes = $("#notes");
const generateButton = $("#generate-button");
const emptyResult = $("#empty-result");
const resultContent = $("#result-content");
const loadingState = $("#loading-state");
const toast = $("#toast");
const MAX_CHARS = 2000;

const today = new Date();
$("#today").textContent = today.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }).toUpperCase();

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function setImage(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) return showToast("Please choose an image file.");
  if (file.size > 10 * 1024 * 1024) return showToast("That image is over 10 MB.");
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    imagePreview.src = reader.result;
    fileName.textContent = file.name;
    dropzoneEmpty.classList.add("hidden");
    previewState.classList.remove("hidden");
  });
  reader.readAsDataURL(file);
}

imageInput.addEventListener("change", (event) => setImage(event.target.files[0]));
["dragenter", "dragover"].forEach((eventName) => dropzone.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropzone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((eventName) => dropzone.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragging");
}));
dropzone.addEventListener("drop", (event) => setImage(event.dataTransfer.files[0]));
$("#remove-image").addEventListener("click", (event) => {
  event.stopPropagation();
  imageInput.value = "";
  imagePreview.src = "";
  previewState.classList.add("hidden");
  dropzoneEmpty.classList.remove("hidden");
});

notes.addEventListener("input", () => {
  if (notes.value.length > MAX_CHARS) notes.value = notes.value.slice(0, MAX_CHARS);
  $("#character-count").textContent = `${notes.value.length.toLocaleString()} / ${MAX_CHARS.toLocaleString()}`;
});

function createBriefing() {
  const input = notes.value.trim();
  const employee = $("#employee").value.trim();
  const shift = $("#shift").value;
  const hasImage = !previewState.classList.contains("hidden");
  const source = input || (hasImage ? "The attached field photo provides today's visual context." : "");
  if (!source) {
    showToast("Add shift notes or a photo to send a report.");
    notes.focus();
    return;
  }

  emptyResult.classList.add("hidden");
  resultContent.classList.add("hidden");
  loadingState.classList.remove("hidden");
  loadingState.style.display = "flex";
  generateButton.disabled = true;

  const formData = new FormData();
  formData.append("employee", employee);
  formData.append("shift", shift);
  formData.append("notes", input);
  if (imageInput.files[0]) formData.append("image", imageInput.files[0]);

  fetch("/api/reports", { method: "POST", body: formData })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "The report could not be submitted.");
      return payload;
    })
    .then((payload) => {
      $("#result-date").textContent = payload.date.toUpperCase();
      $("#result-time").textContent = `${shift.toUpperCase()}${hasImage ? " · PHOTO" : ""}`;
      $("#result-summary").textContent = `${employee ? `${employee} · ` : ""}Your report was reviewed and submitted successfully for manager review.`;
      loadingState.classList.add("hidden");
      loadingState.style.display = "";
      resultContent.classList.remove("hidden");
      generateButton.disabled = false;
    })
    .catch((error) => {
      loadingState.classList.add("hidden");
      loadingState.style.display = "";
      emptyResult.classList.remove("hidden");
      generateButton.disabled = false;
      showToast(error.message);
    });
}

generateButton.addEventListener("click", createBriefing);
$("#new-button").addEventListener("click", () => {
  notes.value = "";
  notes.dispatchEvent(new Event("input"));
  resultContent.classList.add("hidden");
  emptyResult.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
});
