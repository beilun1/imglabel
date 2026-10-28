(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const ui = {
    fileInput: $('file-input'), dropZone: $('drop-zone'), uploadList: $('upload-list'),
    fileCount: $('file-count'), model: $('model-select'), modelDescription: $('model-description'),
    confidence: $('confidence'), confidenceValue: $('confidence-value'),
    start: $('start-button'), startLabel: $('start-label'), clear: $('clear-button'),
    feedback: $('feedback'), progressCard: $('progress-card'), progressTitle: $('progress-title'),
    progressPhase: $('progress-phase'), progressCount: $('progress-count'),
    progressBar: $('progress-bar'), progressFill: $('progress-fill'),
    progressCurrent: $('progress-current'), progressPercent: $('progress-percent'),
    taskErrors: $('task-errors'), resetResults: $('reset-results'), summary: $('results-summary'),
    resultsEmpty: $('results-empty'), emptyMessage: $('results-empty-message'),
    workspace: $('results-workspace'), resultImages: $('result-images'),
    canvas: $('result-canvas'), stage: $('canvas-stage'), canvasMessage: $('canvas-message'),
    dimensions: $('image-dimensions'), imageState: $('image-state'), imageError: $('image-error'),
    canvasHelp: $('canvas-help'), legend: $('class-legend'), instanceList: $('instance-list'),
    instanceCount: $('instance-count'), instanceEmpty: $('instance-empty'),
    detail: $('instance-detail'), detailEmpty: $('detail-empty'), detailIndex: $('detail-index'),
    detailEnglish: $('detail-english'), detailChinese: $('detail-chinese'),
    detailConfidence: $('detail-confidence'), detailArea: $('detail-area'),
    detailSource: $('detail-source'), detailId: $('detail-id'), about: $('about-dialog')
  };
  const classes = [
    { en: 'person', zh: '人', color: '#2f6fe4' },
    { en: 'chair', zh: '椅子', color: '#da8351' },
    { en: 'dining table', zh: '餐桌', color: '#8a63d2' },
    { en: 'couch', zh: '沙发', color: '#d95a92' },
    { en: 'tv', zh: '电视', color: '#38a0aa' },
    { en: 'laptop', zh: '笔记本电脑', color: '#647bd0' },
    { en: 'cup', zh: '杯子', color: '#bd962e' },
    { en: 'bottle', zh: '瓶子', color: '#369976' },
    { en: 'potted plant', zh: '盆栽', color: '#9f774f' },
    { en: 'bed', zh: '床', color: '#bc5968' }
  ];
  const ctx = ui.canvas.getContext('2d');
  const hitContext = document.createElement('canvas').getContext('2d');
  const tabs = Array.from(document.querySelectorAll('.view-tab'));
  const state = {
    files: [], nextFileId: 1, busy: false, taskId: null, snapshot: null,
    images: [], results: new Map(), signatures: new Map(), imageButtons: new Map(),
    activeFilename: null, selectedIndex: -1, view: 'boxes', image: null,
    imageLoading: false, imageLoadError: '', imageToken: 0, transform: null,
    paths: new WeakMap(), inspectorKey: '', taskFailure: '',
    pollTimer: null, pollFailures: 0, runToken: 0, uncertainError: null,
    feedbackKind: '', frame: null
  };
  const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 });

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }

  function showFeedback(message, kind = 'error') {
    state.feedbackKind = kind;
    ui.feedback.textContent = message;
    ui.feedback.classList.toggle('info', kind !== 'error');
    ui.feedback.hidden = !message;
  }

  function clearFeedback() {
    state.feedbackKind = '';
    ui.feedback.textContent = '';
    ui.feedback.hidden = true;
  }

  function setBusy(busy) {
    state.busy = busy;
    ui.start.disabled = busy || !state.files.length;
    ui.startLabel.textContent = busy ? '检测中…' : '开始检测';
    ui.clear.disabled = busy || (!state.files.length && !state.taskId && ui.progressCard.hidden);
    ui.resetResults.disabled = busy || (ui.progressCard.hidden && !state.taskId);
    ui.model.disabled = busy;
    ui.confidence.disabled = busy;
    ui.fileInput.disabled = busy;
    ui.dropZone.classList.toggle('is-disabled', busy);
    ui.dropZone.setAttribute('aria-disabled', String(busy));
    ui.dropZone.tabIndex = busy ? -1 : 0;
    ui.uploadList.querySelectorAll('button').forEach((button) => { button.disabled = busy; });
  }

  function formatSize(bytes) {
    return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function renderUploads() {
    ui.uploadList.replaceChildren();
    state.files.forEach((entry) => {
      const item = node('div', 'upload-item');
      const thumb = node('img', 'upload-thumb');
      thumb.src = entry.preview;
      thumb.alt = entry.file.name;
      thumb.addEventListener('error', () => {
        thumb.removeAttribute('src');
        thumb.alt = '无法预览';
      }, { once: true });
      const info = node('div', 'upload-file-info');
      const name = node('div', 'upload-file-name', entry.file.name);
      name.title = entry.file.name;
      info.append(name, node('span', 'upload-file-size', formatSize(entry.file.size)));
      const remove = node('button', 'delete-file', '×');
      remove.type = 'button';
      remove.disabled = state.busy;
      remove.setAttribute('aria-label', `删除 ${entry.file.name}`);
      remove.addEventListener('click', () => {
        if (state.busy) return;
        const index = state.files.findIndex((file) => file.id === entry.id);
        if (index === -1) return;
        state.files.splice(index, 1);
        resetResults();
        URL.revokeObjectURL(entry.preview);
        renderUploads();
      });
      item.append(thumb, info, remove);
      ui.uploadList.append(item);
    });
    ui.fileCount.textContent = state.files.length ? `已选择 ${state.files.length} 张` : '未选择图片';
    setBusy(state.busy);
  }

  function addFiles(fileList) {
    if (state.busy) return;
    const rejected = [];
    let added = 0;
    Array.from(fileList).forEach((file) => {
      if (!file.type.startsWith('image/') && !/\.(jpe?g|png|webp|bmp|gif|tiff?|avif|heic|heif)$/i.test(file.name)) {
        rejected.push(file.name);
        return;
      }
      const exists = state.files.some((entry) => entry.file.name === file.name && entry.file.size === file.size && entry.file.lastModified === file.lastModified);
      if (exists) return;
      state.files.push({ id: state.nextFileId++, file, preview: URL.createObjectURL(file) });
      added += 1;
    });
    if (added) resetResults();
    if (rejected.length) showFeedback(`以下文件不是可识别的图片，已跳过：${rejected.join('、')}`, 'info');
    else clearFeedback();
    renderUploads();
  }

  function updateConfidence() {
    const value = Number(ui.confidence.value);
    ui.confidenceValue.textContent = value.toFixed(2);
    ui.confidence.style.setProperty('--range-progress', `${((value - 0.05) / 0.85) * 100}%`);
    ui.confidence.setAttribute('aria-valuetext', `置信度阈值 ${value.toFixed(2)}`);
  }

  function updateModelDescription() {
    ui.modelDescription.textContent = ui.model.value === 'R0'
      ? '官方 YOLO-World 目标检测与分割组合。'
      : '训练后的实例分割模型，直接输出实例掩码。';
  }

  class RequestError extends Error {
    constructor(message, status = 0) {
      super(message);
      this.name = 'RequestError';
      this.status = status;
    }
  }

  function errorText(value) {
    if (typeof value === 'string') return value;
    if (value instanceof Error) return value.message;
    if (value && typeof value === 'object') {
      const detail = value.error || value.message || value.detail;
      if (detail && detail !== value) {
        const message = errorText(detail);
        const name = value.name || value.filename || value.image;
        return name ? `${String(name)}：${message}` : message;
      }
      try { return JSON.stringify(value); } catch (_) { return '未知错误'; }
    }
    return value == null ? '未知错误' : String(value);
  }

  async function api(url, options = {}, timeout = 120000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal, cache: 'no-store' });
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); } catch (_) { data = null; }
      if (!response.ok) {
        const detail = data && (data.msg || data.error || data.message || data.detail);
        throw new RequestError(detail ? errorText(detail).slice(0, 1200) : `请求失败（HTTP ${response.status}）。`, response.status);
      }
      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        throw new RequestError('服务返回了无效的 JSON 数据，请检查后端响应。', response.status);
      }
      return data;
    } catch (error) {
      if (error instanceof RequestError) throw error;
      if (error.name === 'AbortError') throw new RequestError('请求超时，请检查后端是否正常运行。');
      throw new RequestError('无法连接服务，请检查网络和本地后端。');
    } finally {
      window.clearTimeout(timer);
    }
  }

  function normalizedImages(images) {
    const used = new Set();
    return images.filter((image) => image && typeof image.filename === 'string').map((image, index) => {
      let fileIndex = state.files.findIndex((entry, i) => !used.has(i) && entry.file.name === image.name);
      if (fileIndex === -1 && !used.has(index) && state.files[index]) fileIndex = index;
      if (fileIndex !== -1) used.add(fileIndex);
      const entry = state.files[fileIndex];
      return {
        ...image,
        name: typeof image.name === 'string' ? image.name : entry ? entry.file.name : image.filename,
        preview: entry ? entry.preview : null
      };
    });
  }

  function imageUrl(image) {
    if (typeof image.url === 'string') {
      try {
        const url = new URL(image.url, window.location.origin);
        if (url.origin === window.location.origin && /^(https?:)$/.test(url.protocol)) return url.href;
      } catch (_) { }
    }
    return `/uploads/${encodeURIComponent(image.filename)}`;
  }

  function installImages(images) {
    const currentScroll = ui.resultImages.scrollLeft;
    state.images = normalizedImages(images);
    ui.resultImages.replaceChildren();
    state.imageButtons.clear();
    state.images.forEach((image) => {
      const button = node('button', 'result-image');
      button.type = 'button';
      button.title = image.name;
      button.setAttribute('aria-label', `查看 ${image.name} 的检测结果`);
      button.setAttribute('aria-pressed', 'false');
      const thumb = node('img');
      thumb.src = imageUrl(image);
      thumb.alt = '';
      let triedPreview = false;
      thumb.addEventListener('error', () => {
        if (image.preview && !triedPreview) {
          triedPreview = true;
          thumb.src = image.preview;
        } else {
          thumb.removeAttribute('src');
        }
      });
      const info = node('span', 'result-image-info');
      const name = node('span', 'result-image-name', image.name);
      const status = node('span', 'result-image-status', '等待检测');
      info.append(name, status);
      button.append(thumb, info);
      button.addEventListener('click', () => selectImage(image.filename));
      state.imageButtons.set(image.filename, { button, status });
      ui.resultImages.append(button);
    });
    ui.resultImages.scrollLeft = currentScroll;
    ui.resultsEmpty.hidden = state.images.length > 0;
    ui.workspace.hidden = !state.images.length;
    if (!state.images.some((image) => image.filename === state.activeFilename)) {
      selectImage(state.images.length ? state.images[0].filename : null);
    }
    updateImageButtons();
  }

  function activeImage() {
    return state.images.find((image) => image.filename === state.activeFilename) || null;
  }

  function activeResult() {
    return state.results.get(state.activeFilename) || null;
  }

  function instancesOf(result) {
    return result && Array.isArray(result.instances) ? result.instances.filter((instance) => instance && typeof instance === 'object') : [];
  }

  function updateImageButtons() {
    state.imageButtons.forEach(({ button, status }, filename) => {
      const result = state.results.get(filename);
      const active = filename === state.activeFilename;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
      status.classList.toggle('has-error', Boolean(result && result.error));
      status.textContent = result
        ? result.error ? '检测失败' : `${instancesOf(result).length} 个目标`
        : state.taskFailure ? '未完成' : state.snapshot && state.snapshot.status === 'done' ? '无返回结果' : '等待检测';
    });
  }

  function selectImage(filename) {
    if (filename === state.activeFilename && state.image) return;
    state.activeFilename = filename;
    state.selectedIndex = -1;
    state.inspectorKey = '';
    state.image = null;
    state.imageLoadError = '';
    state.imageLoading = Boolean(filename);
    state.transform = null;
    const token = ++state.imageToken;
    const metadata = activeImage();
    updateImageButtons();
    renderActiveResult();
    if (!metadata) return;
    const image = new Image();
    image.decoding = 'async';
    image.onload = () => {
      if (token !== state.imageToken) return;
      state.image = image;
      state.imageLoading = false;
      updateActiveStatus();
      requestCanvasDraw();
    };
    image.onerror = () => {
      if (token !== state.imageToken) return;
      state.imageLoading = false;
      state.imageLoadError = '原始图片载入失败，请检查上传文件是否仍可访问。';
      updateActiveStatus();
      requestCanvasDraw();
    };
    image.src = imageUrl(metadata);
  }

  function classInfo(instance) {
    const byName = typeof instance.cls_name === 'string' ? classes.find((item) => item.en === instance.cls_name.toLowerCase().replace(/_/g, ' ')) : null;
    const index = Number(instance.cls);
    const known = byName || (Number.isInteger(index) && classes[index]) || null;
    return {
      en: typeof instance.cls_name === 'string' && instance.cls_name ? instance.cls_name : known ? known.en : 'unknown',
      zh: known ? known.zh : '未知类别',
      color: known ? known.color : '#7f8ba1'
    };
  }

  function instanceColor(index) {
    return `hsl(${(index * 137.508 + 211) % 360}, 70%, 49%)`;
  }

  function colorFor(instance, index) {
    return state.view === 'instances' ? instanceColor(index) : classInfo(instance).color;
  }

  function confidenceText(instance) {
    const value = Number(instance.conf);
    return Number.isFinite(value) ? value.toFixed(3) : '—';
  }

  function renderActiveResult() {
    const result = activeResult();
    const instances = instancesOf(result);
    if (state.selectedIndex >= instances.length) state.selectedIndex = -1;
    ui.instanceCount.textContent = String(instances.length);
    const key = `${state.activeFilename}|${state.signatures.get(state.activeFilename) || ''}|${state.view}`;
    if (key !== state.inspectorKey) {
      state.inspectorKey = key;
      ui.instanceList.replaceChildren();
      instances.forEach((instance, index) => {
        const info = classInfo(instance);
        const button = node('button', 'instance-item');
        button.type = 'button';
        button.dataset.index = String(index);
        button.setAttribute('aria-label', `目标 ${index}，${info.en}，${info.zh}，置信度 ${confidenceText(instance)}`);
        const swatch = node('span', 'color-swatch');
        swatch.style.backgroundColor = colorFor(instance, index);
        const name = node('span', 'instance-name');
        name.append(node('strong', '', info.en), node('small', '', info.zh));
        button.append(node('span', 'instance-index', `#${index}`), swatch, name, node('span', 'instance-confidence', confidenceText(instance)));
        button.addEventListener('click', () => selectInstance(index));
        ui.instanceList.append(button);
      });
      renderLegend(instances);
    }
    updateActiveStatus();
    updateInstanceButtons();
    renderDetail();
    requestCanvasDraw();
  }

  function updateActiveStatus() {
    const result = activeResult();
    const instances = instancesOf(result);
    const done = state.snapshot && state.snapshot.status === 'done';
    const errors = [];
    if (state.imageLoadError) errors.push(state.imageLoadError);
    if (result && result.error) errors.push(`此图片检测失败：${errorText(result.error)}`);
    if (!result && done && state.activeFilename) errors.push('任务已结束，但后端未返回此图片的检测结果。');
    if (state.taskFailure) errors.push(`本次检测未完成：${state.taskFailure}`);
    ui.imageError.textContent = errors.join(' ');
    ui.imageError.hidden = !errors.length;
    ui.imageState.className = 'image-state';
    if (result && result.error) {
      ui.imageState.textContent = '此图检测失败';
      ui.imageState.classList.add('error');
    } else if (result) {
      ui.imageState.textContent = instances.length ? `已检测 · ${instances.length} 个目标` : '未检测到符合阈值的目标';
      ui.imageState.classList.add('ready');
    } else if (state.taskFailure || done) {
      ui.imageState.textContent = '未获得检测结果';
      ui.imageState.classList.add('error');
    } else {
      const current = state.snapshot && state.snapshot.progress && state.snapshot.progress.current_file;
      const metadata = activeImage();
      ui.imageState.textContent = current && metadata && (current === metadata.filename || current === metadata.name) ? '正在检测此图片…' : '等待此图片检测…';
    }
    ui.instanceEmpty.hidden = instances.length > 0;
    ui.instanceEmpty.textContent = result && result.error
      ? '此图片检测失败，请查看错误信息。'
      : result ? '没有符合当前阈值的目标。'
      : state.taskFailure || done ? '没有可展示的检测结果。' : '正在等待此图片的检测结果…';
    ui.canvasMessage.hidden = Boolean(state.image);
    ui.canvasMessage.textContent = state.imageLoading ? '正在载入图片…' : state.imageLoadError || '暂无图片';
    ui.canvas.classList.toggle('has-image', Boolean(state.image));
    const size = imageDimensions();
    ui.dimensions.textContent = size ? `${size.width} × ${size.height} px` : '—';
    if (size) ui.canvas.setAttribute('aria-label', `${activeImage().name}，${instances.length} 个目标，点击目标可查看详情`);
  }

  function renderLegend(instances) {
    ui.legend.replaceChildren();
    if (state.view === 'instances') {
      if (instances.length) ui.legend.append(node('span', 'legend-item', '每个实例独立着色 · 虚线框表示无掩码目标'));
      return;
    }
    const shown = new Set();
    instances.forEach((instance) => {
      const info = classInfo(instance);
      if (shown.has(info.en)) return;
      shown.add(info.en);
      const item = node('span', 'legend-item');
      const swatch = node('span', 'color-swatch');
      swatch.style.backgroundColor = info.color;
      item.append(swatch, document.createTextNode(`${info.en} · ${info.zh}`));
      ui.legend.append(item);
    });
  }

  function updateInstanceButtons() {
    ui.instanceList.querySelectorAll('button').forEach((button) => {
      const selected = Number(button.dataset.index) === state.selectedIndex;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
  }

  function selectInstance(index) {
    const instances = instancesOf(activeResult());
    state.selectedIndex = index >= 0 && index < instances.length ? index : -1;
    updateInstanceButtons();
    renderDetail();
    requestCanvasDraw();
    const selected = ui.instanceList.querySelector('.selected');
    if (selected) {
      const itemTop = selected.offsetTop - ui.instanceList.offsetTop;
      if (itemTop < ui.instanceList.scrollTop || itemTop + selected.offsetHeight > ui.instanceList.scrollTop + ui.instanceList.clientHeight) {
        ui.instanceList.scrollTop = Math.max(0, itemTop - ui.instanceList.clientHeight / 2 + selected.offsetHeight / 2);
      }
    }
  }

  function renderDetail() {
    const instance = instancesOf(activeResult())[state.selectedIndex];
    ui.detail.hidden = !instance;
    ui.detailEmpty.hidden = Boolean(instance);
    if (!instance) {
      ui.detailId.value = '';
      return;
    }
    const info = classInfo(instance);
    ui.detailIndex.textContent = `#${state.selectedIndex}`;
    ui.detailEnglish.textContent = info.en;
    ui.detailChinese.textContent = info.zh;
    ui.detailConfidence.textContent = confidenceText(instance);
    const area = Number(instance.area);
    ui.detailArea.textContent = instance.area != null && Number.isFinite(area) ? `${numberFormatter.format(area)} px²` : '—';
    ui.detailSource.textContent = { seg: '实例分割', det: '检测框占位（非精确掩码）', reback: '自训分割（R1）' }[instance.src] || '—';
    ui.detailId.value = instance.id == null ? '—' : String(instance.id);
  }

  function positiveNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : null;
  }

  function imageDimensions() {
    const metadata = activeImage();
    const result = activeResult();
    if (!metadata) return null;
    const width = positiveNumber(result && result.width) || positiveNumber(metadata.width) || (state.image && state.image.naturalWidth);
    const height = positiveNumber(result && result.height) || positiveNumber(metadata.height) || (state.image && state.image.naturalHeight);
    return width && height ? { width, height } : null;
  }

  function bboxOf(instance) {
    if (!Array.isArray(instance.bbox) || instance.bbox.length < 4) return null;
    const box = instance.bbox.slice(0, 4).map(Number);
    if (!box.every(Number.isFinite)) return null;
    const [x1, y1, x2, y2] = box;
    return x2 > x1 && y2 > y1 ? { x: x1, y: y1, width: x2 - x1, height: y2 - y1 } : null;
  }

  function pathOf(instance) {
    if (state.paths.has(instance)) return state.paths.get(instance);
    let path = null;
    if (Array.isArray(instance.mask) && instance.mask.length >= 3) {
      const points = instance.mask.filter((point) => Array.isArray(point) && point.length >= 2 && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1])));
      if (points.length >= 3) {
        path = new Path2D();
        path.moveTo(Number(points[0][0]), Number(points[0][1]));
        for (let i = 1; i < points.length; i += 1) path.lineTo(Number(points[i][0]), Number(points[i][1]));
        path.closePath();
      }
    }
    state.paths.set(instance, path);
    return path;
  }

  function requestCanvasDraw() {
    if (state.frame !== null) return;
    state.frame = window.requestAnimationFrame(() => {
      state.frame = null;
      drawCanvas();
    });
  }

  function drawCanvas() {
    const width = ui.canvas.clientWidth;
    const height = ui.canvas.clientHeight;
    if (!width || !height || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const pixelWidth = Math.max(1, Math.round(width * dpr));
    const pixelHeight = Math.max(1, Math.round(height * dpr));
    if (ui.canvas.width !== pixelWidth || ui.canvas.height !== pixelHeight) {
      ui.canvas.width = pixelWidth;
      ui.canvas.height = pixelHeight;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    state.transform = null;
    const size = imageDimensions();
    if (!state.image || !size) return;
    const scale = Math.min(width / size.width, height / size.height);
    const offsetX = (width - size.width * scale) / 2;
    const offsetY = (height - size.height * scale) / 2;
    state.transform = { scale, offsetX, offsetY, width: size.width, height: size.height, viewportWidth: width, viewportHeight: height };
    ctx.drawImage(state.image, offsetX, offsetY, size.width * scale, size.height * scale);
    const instances = instancesOf(activeResult());
    ctx.save();
    ctx.translate(offsetX, offsetY);
    ctx.scale(scale, scale);
    ctx.beginPath();
    ctx.rect(0, 0, size.width, size.height);
    ctx.clip();
    instances.forEach((instance, index) => {
      const color = colorFor(instance, index);
      const box = bboxOf(instance);
      const path = state.view === 'boxes' ? null : pathOf(instance);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.7 / scale;
      if (path) {
        ctx.fillStyle = color;
        ctx.globalAlpha = index === state.selectedIndex ? .48 : state.view === 'semantic' ? .38 : .32;
        ctx.fill(path, 'nonzero');
        ctx.globalAlpha = .9;
        ctx.stroke(path);
        ctx.globalAlpha = 1;
      } else if (box) {
        ctx.setLineDash(state.view === 'boxes' ? [] : [5 / scale, 4 / scale]);
        ctx.strokeRect(box.x, box.y, box.width, box.height);
        ctx.setLineDash([]);
      }
    });
    const selected = instances[state.selectedIndex];
    if (selected) {
      const path = state.view === 'boxes' ? null : pathOf(selected);
      const box = bboxOf(selected);
      const stroke = () => {
        if (path) ctx.stroke(path);
        else if (box) ctx.strokeRect(box.x, box.y, box.width, box.height);
      };
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 4.5 / scale;
      stroke();
      ctx.strokeStyle = colorFor(selected, state.selectedIndex);
      ctx.lineWidth = 2.5 / scale;
      stroke();
    }
    ctx.restore();
    if (state.view === 'boxes') instances.forEach((instance, index) => drawLabel(instance, index));
    else if (selected) drawLabel(selected, state.selectedIndex);
  }

  function drawLabel(instance, index) {
    const box = bboxOf(instance);
    const transform = state.transform;
    if (!box || !transform) return;
    const { scale, offsetX, offsetY, width, height } = transform;
    const label = `${classInfo(instance).en} ${confidenceText(instance)}`;
    ctx.save();
    ctx.font = '600 11px "Segoe UI", "Microsoft YaHei", sans-serif';
    const imageWidth = width * scale;
    const imageHeight = height * scale;
    const labelWidth = Math.min(ctx.measureText(label).width + 12, imageWidth);
    const labelHeight = Math.min(21, imageHeight);
    const x = Math.min(Math.max(offsetX + box.x * scale, offsetX), offsetX + imageWidth - labelWidth);
    const aboveY = offsetY + box.y * scale - labelHeight;
    const y = Math.min(Math.max(aboveY, offsetY), offsetY + imageHeight - labelHeight);
    ctx.fillStyle = colorFor(instance, index);
    ctx.fillRect(x, y, labelWidth, labelHeight);
    ctx.beginPath();
    ctx.rect(x, y, labelWidth, labelHeight);
    ctx.clip();
    ctx.fillStyle = '#ffffff';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, x + 6, y + labelHeight / 2 + .5);
    ctx.restore();
  }

  function handleCanvasClick(event) {
    if (!state.transform || !state.image || !hitContext) return;
    const rect = ui.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const transform = state.transform;
    const screenX = (event.clientX - rect.left) * transform.viewportWidth / rect.width;
    const screenY = (event.clientY - rect.top) * transform.viewportHeight / rect.height;
    const x = (screenX - transform.offsetX) / transform.scale;
    const y = (screenY - transform.offsetY) / transform.scale;
    if (x < 0 || y < 0 || x > transform.width || y > transform.height) {
      selectInstance(-1);
      return;
    }
    const instances = instancesOf(activeResult());
    hitContext.setTransform(1, 0, 0, 1, 0, 0);
    for (let index = instances.length - 1; index >= 0; index -= 1) {
      const instance = instances[index];
      const path = state.view === 'boxes' ? null : pathOf(instance);
      const box = bboxOf(instance);
      const hit = path ? hitContext.isPointInPath(path, x, y, 'nonzero') : box && x >= box.x && x <= box.x + box.width && y >= box.y && y <= box.y + box.height;
      if (hit) {
        selectInstance(index);
        return;
      }
    }
    selectInstance(-1);
  }

  function setView(view) {
    state.view = view;
    tabs.forEach((tab) => {
      const active = tab.dataset.view === view;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active) $('canvas-panel').setAttribute('aria-labelledby', tab.id);
    });
    ui.canvasHelp.textContent = {
      boxes: '点击检测框或右侧列表查看详情',
      instances: '实例独立着色 · 点击掩码查看详情',
      semantic: '同类同色 · 保留掩码空洞'
    }[view];
    state.inspectorKey = '';
    renderActiveResult();
  }

  function validateSnapshot(snapshot) {
    if (!snapshot || !['pending', 'running', 'done'].includes(snapshot.status)) throw new RequestError('后端返回了无效的任务状态。');
    if (snapshot.task_id != null && String(snapshot.task_id) !== state.taskId) throw new RequestError('返回的任务 ID 不匹配。');
  }

  function collectTaskErrors(snapshot) {
    const messages = Array.isArray(snapshot.errors) ? snapshot.errors.map(errorText) : [];
    state.results.forEach((result, filename) => {
      if (!result.error) return;
      const image = state.images.find((item) => item.filename === filename);
      messages.push(`${result.name || (image && image.name) || filename}：${errorText(result.error)}`);
    });
    return Array.from(new Set(messages.filter(Boolean)));
  }

  function updateProgress(snapshot) {
    const progress = snapshot.progress || {};
    const total = Math.max(0, Number.isFinite(Number(progress.total)) ? Number(progress.total) : state.images.length);
    const done = Math.max(0, Number.isFinite(Number(progress.done)) ? Number(progress.done) : state.results.size);
    const complete = snapshot.status === 'done';
    const percent = complete ? 100 : total ? Math.min(100, Math.round(done / total * 100)) : 0;
    const errors = collectTaskErrors(snapshot);
    const phase = { queued: '排队等待', loading: '加载模型', image: '图片推理', done: '已完成' }[snapshot.phase] || (complete ? '已完成' : '等待调度');
    ui.progressCard.hidden = false;
    ui.progressCard.classList.toggle('is-done', complete && !errors.length);
    ui.progressCard.classList.toggle('is-error', complete && errors.length > 0);
    ui.progressTitle.textContent = complete ? errors.length ? '检测结束 · 存在错误' : '检测完成' : '检测进行中';
    ui.progressPhase.textContent = complete ? '已结束' : phase;
    ui.progressCount.textContent = `${done} / ${total}`;
    ui.progressFill.style.width = `${percent}%`;
    ui.progressBar.setAttribute('aria-valuenow', String(percent));
    ui.progressBar.setAttribute('aria-valuetext', `已处理 ${done} 张，共 ${total} 张${complete ? '，任务已结束' : ''}`);
    ui.progressPercent.textContent = `${percent}%`;
    const current = progress.current_file;
    const currentImage = state.images.find((image) => image.filename === current || image.name === current);
    const currentName = currentImage ? currentImage.name : current;
    const model = snapshot.model || ui.model.value;
    const confidence = Number(snapshot.conf == null ? ui.confidence.value : snapshot.conf);
    ui.progressCurrent.textContent = complete
      ? `已处理 ${done} 张图片 · ${model} · 阈值 ${Number.isFinite(confidence) ? confidence.toFixed(2) : '—'}`
      : currentName ? `当前图片：${String(currentName)}` : snapshot.phase === 'loading' ? '模型首次加载可能需要一些时间，请稍候…' : '任务已创建，等待图片检测…';
    ui.progressCurrent.title = ui.progressCurrent.textContent;
    ui.taskErrors.replaceChildren();
    errors.forEach((message) => ui.taskErrors.append(node('p', '', message)));
    ui.taskErrors.hidden = !errors.length;
    const count = Array.from(state.results.values()).reduce((sum, result) => sum + instancesOf(result).length, 0);
    ui.summary.textContent = `${state.images.length} 张图片 · ${count} 个目标`;
  }

  function applySnapshot(snapshot) {
    validateSnapshot(snapshot);
    const finished = snapshot.status === 'done' && (!state.snapshot || state.snapshot.status !== 'done');
    state.snapshot = snapshot;
    if (Array.isArray(snapshot.images) && snapshot.images.length) {
      const filenames = snapshot.images.filter((image) => image && typeof image.filename === 'string').map((image) => image.filename);
      if (filenames.join('\u0000') !== state.images.map((image) => image.filename).join('\u0000')) installImages(snapshot.images);
    }
    if (Array.isArray(snapshot.results)) {
      snapshot.results.forEach((result) => {
        if (!result || typeof result.image !== 'string') return;
        const signature = JSON.stringify(result);
        if (state.signatures.get(result.image) === signature) return;
        state.results.set(result.image, result);
        state.signatures.set(result.image, signature);
      });
    }
    updateProgress(snapshot);
    updateImageButtons();
    renderActiveResult();
    if (snapshot.status === 'done') {
      window.clearTimeout(state.pollTimer);
      state.pollTimer = null;
      state.uncertainError = null;
      if (state.feedbackKind === 'poll') clearFeedback();
      if (finished && state.images.length) selectImage(state.images[0].filename);
      setBusy(false);
    }
  }

  function beginPolling(token, delay = 800) {
    window.clearTimeout(state.pollTimer);
    if (!state.busy || token !== state.runToken) return;
    state.pollTimer = window.setTimeout(() => pollOnce(token), delay);
  }

  async function pollOnce(token) {
    state.pollTimer = null;
    if (!state.busy || token !== state.runToken || !state.taskId) return;
    try {
      const snapshot = await api(`/api/progress/${encodeURIComponent(state.taskId)}`, {}, 20000);
      if (token !== state.runToken) return;
      validateSnapshot(snapshot);
      if (state.uncertainError && snapshot.status === 'pending') {
        failRun(state.uncertainError, 'detect');
        return;
      }
      state.uncertainError = null;
      state.pollFailures = 0;
      if (state.feedbackKind === 'poll') clearFeedback();
      applySnapshot(snapshot);
      if (state.busy) beginPolling(token);
    } catch (error) {
      if (token !== state.runToken) return;
      if (error instanceof RequestError && [400, 404, 410, 422].includes(error.status)) {
        failRun(new RequestError(`任务不可用：${errorText(error)} 已保留图片，可重新启动检测。`), 'detect');
        return;
      }
      state.pollFailures += 1;
      showFeedback(`暂时无法获取进度：${errorText(error)} 正在自动重试（第 ${state.pollFailures} 次），请勿重复启动检测。`, 'poll');
      beginPolling(token, Math.min(8000, 1000 * Math.pow(2, Math.min(state.pollFailures - 1, 3))));
    }
  }

  function resetTaskState() {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
    state.taskId = null;
    state.snapshot = null;
    state.images = [];
    state.results.clear();
    state.signatures.clear();
    state.imageButtons.clear();
    state.activeFilename = null;
    state.selectedIndex = -1;
    state.image = null;
    state.imageLoading = false;
    state.imageLoadError = '';
    state.imageToken += 1;
    state.transform = null;
    state.paths = new WeakMap();
    state.inspectorKey = '';
    state.taskFailure = '';
    state.pollFailures = 0;
    state.uncertainError = null;
    ui.resultImages.replaceChildren();
    ui.instanceList.replaceChildren();
    ui.legend.replaceChildren();
    ui.taskErrors.replaceChildren();
    ui.taskErrors.hidden = true;
    ui.detail.hidden = true;
    ui.detailEmpty.hidden = false;
    ui.detailId.value = '';
    ui.instanceCount.textContent = '0';
    ui.instanceEmpty.hidden = false;
    ui.workspace.hidden = true;
    ui.resultsEmpty.hidden = false;
    ui.summary.textContent = '等待检测';
    ui.emptyMessage.textContent = '选择图片与模型，点击「开始检测」查看结果。';
    ui.progressCard.classList.remove('is-done', 'is-error');
    requestCanvasDraw();
  }

  function resetResults() {
    if (state.busy) return;
    state.runToken += 1;
    resetTaskState();
    ui.progressCard.hidden = true;
    clearFeedback();
    setBusy(false);
  }

  function failRun(error, stage) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
    state.uncertainError = null;
    state.taskFailure = errorText(error);
    const title = stage === 'upload' ? '上传失败' : '检测未完成';
    ui.progressCard.hidden = false;
    ui.progressCard.classList.remove('is-done');
    ui.progressCard.classList.add('is-error');
    ui.progressTitle.textContent = title;
    ui.progressPhase.textContent = '已停止';
    ui.progressCurrent.textContent = state.taskFailure;
    ui.progressCurrent.title = state.taskFailure;
    ui.summary.textContent = title;
    ui.emptyMessage.textContent = `${title}，已保留所选图片，可检查后重试。`;
    showFeedback(`${title}：${state.taskFailure}`);
    updateImageButtons();
    renderActiveResult();
    setBusy(false);
  }

  async function startDetection() {
    if (state.busy || !state.files.length) return;
    resetTaskState();
    const token = ++state.runToken;
    setBusy(true);
    clearFeedback();
    ui.progressCard.hidden = false;
    ui.progressTitle.textContent = '准备检测';
    ui.progressPhase.textContent = '上传中';
    ui.progressCount.textContent = `0 / ${state.files.length}`;
    ui.progressFill.style.width = '0%';
    ui.progressBar.setAttribute('aria-valuenow', '0');
    ui.progressBar.setAttribute('aria-valuetext', '正在上传图片');
    ui.progressPercent.textContent = '0%';
    ui.progressCurrent.textContent = '正在上传所选图片…';
    ui.summary.textContent = '准备检测';
    ui.emptyMessage.textContent = '图片上传中，检测结果将在这里显示。';
    let stage = 'upload';
    try {
      const form = new FormData();
      state.files.forEach((entry) => form.append('files', entry.file, entry.file.name));
      const uploaded = await api('/api/upload', { method: 'POST', body: form });
      if (token !== state.runToken) return;
      if (uploaded.task_id == null || !Array.isArray(uploaded.images) || !uploaded.images.length) throw new RequestError('上传响应缺少任务 ID 或图片列表。');
      state.taskId = String(uploaded.task_id);
      installImages(uploaded.images);
      if (!state.images.length) throw new RequestError('后端未返回可用的上传图片。');
      stage = 'detect';
      const model = ui.model.value;
      const confidence = Number(ui.confidence.value);
      applySnapshot({ task_id: state.taskId, status: 'pending', phase: 'queued', images: [], results: [], progress: { done: 0, total: state.images.length, current_file: '' }, errors: [], model, conf: confidence });
      let snapshot;
      try {
        snapshot = await api('/api/detect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: state.taskId, model, conf: confidence }) });
        validateSnapshot(snapshot);
      } catch (detectError) {
        let recovered;
        try {
          recovered = await api(`/api/progress/${encodeURIComponent(state.taskId)}`, {}, 20000);
          validateSnapshot(recovered);
        } catch (_) {
          if (token !== state.runToken) return;
          state.uncertainError = detectError;
          showFeedback(`检测请求未能确认：${errorText(detectError)} 正在查询任务状态，请勿重复启动。`, 'poll');
          beginPolling(token, 1000);
          return;
        }
        if (recovered.status === 'pending') throw detectError;
        snapshot = recovered;
      }
      if (token !== state.runToken) return;
      applySnapshot(snapshot);
      if (state.busy) beginPolling(token);
    } catch (error) {
      if (token === state.runToken) failRun(error, stage);
    }
  }

  ui.fileInput.addEventListener('change', () => {
    addFiles(ui.fileInput.files);
    ui.fileInput.value = '';
  });
  ui.dropZone.addEventListener('click', (event) => {
    if (state.busy) event.preventDefault();
  });
  ui.dropZone.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    if (!state.busy) ui.fileInput.click();
  });
  let dragDepth = 0;
  ui.dropZone.addEventListener('dragenter', (event) => {
    event.preventDefault();
    dragDepth += 1;
    if (!state.busy) ui.dropZone.classList.add('drag-over');
  });
  ui.dropZone.addEventListener('dragover', (event) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = state.busy ? 'none' : 'copy';
  });
  ui.dropZone.addEventListener('dragleave', (event) => {
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) ui.dropZone.classList.remove('drag-over');
  });
  ui.dropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    dragDepth = 0;
    ui.dropZone.classList.remove('drag-over');
    if (event.dataTransfer) addFiles(event.dataTransfer.files);
  });
  window.addEventListener('dragover', (event) => {
    if (event.dataTransfer && Array.from(event.dataTransfer.types).includes('Files')) event.preventDefault();
  });
  window.addEventListener('drop', (event) => {
    if (event.dataTransfer && Array.from(event.dataTransfer.types).includes('Files')) event.preventDefault();
  });
  ui.confidence.addEventListener('input', updateConfidence);
  ui.model.addEventListener('change', updateModelDescription);
  ui.start.addEventListener('click', startDetection);
  ui.clear.addEventListener('click', () => {
    if (state.busy) return;
    resetResults();
    state.files.forEach((entry) => URL.revokeObjectURL(entry.preview));
    state.files = [];
    ui.fileInput.value = '';
    renderUploads();
  });
  ui.resetResults.addEventListener('click', () => {
    if (state.busy) return;
    resetResults();
    ui.dropZone.focus({ preventScroll: true });
    ui.dropZone.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  });
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => setView(tab.dataset.view));
    tab.addEventListener('keydown', (event) => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      setView(tabs[next].dataset.view);
      tabs[next].focus();
    });
  });
  ui.canvas.addEventListener('click', handleCanvasClick);
  $('detection-nav').addEventListener('click', () => window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }));
  classes.forEach((item) => $('about-classes').append(node('span', '', `${item.en} · ${item.zh}`)));
  $('about-button').addEventListener('click', () => { if (!ui.about.open) ui.about.showModal(); });
  $('close-about').addEventListener('click', () => ui.about.close());
  $('about-done').addEventListener('click', () => ui.about.close());
  ui.about.addEventListener('click', (event) => {
    const rect = ui.about.getBoundingClientRect();
    if (event.target === ui.about && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) ui.about.close();
  });
  if ('ResizeObserver' in window) new ResizeObserver(requestCanvasDraw).observe(ui.stage);
  window.addEventListener('resize', requestCanvasDraw);
  function watchPixelRatio() {
    const query = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
    if (query.addEventListener) query.addEventListener('change', () => { requestCanvasDraw(); watchPixelRatio(); }, { once: true });
  }
  watchPixelRatio();
  window.addEventListener('pagehide', (event) => {
    if (!event.persisted) state.files.forEach((entry) => URL.revokeObjectURL(entry.preview));
  });
  updateConfidence();
  updateModelDescription();
  renderUploads();
})();
