/**
 * Luna Gifts — Cutscene v6
 * - First visit: full cinematic + tutorial
 * - Return visits: 3D loading screen (top-down desk with phone showing real site)
 * - All desk items from GLB models: table.glb, phone.glb, lamp.glb, Laptop.glb
 * - Phone screen shows actual website via HTML overlay positioned in 3D
 */
(function () {
  'use strict';

  const LOGO  = '/static/img/logo.png';
  const STAR  = '/static/img/star.png';
  const LOADING_GIF = '/static/img/loading.gif';
  const THREE_VER = '0.157.0';
  const LOADER_VER = '0.147.0';
  const CDN   = `https://cdn.jsdelivr.net/npm/three@${THREE_VER}`;
  const LOADER_CDN = `https://cdn.jsdelivr.net/npm/three@${LOADER_VER}`;

  const MODELS = {
    phone:     '/static/models/phone.glb',
    table:     '/static/models/table.glb',
    lamp:      '/static/models/lamp.glb',
    laptop:    '/static/models/Laptop.glb',
    paper:     '/static/models/paper.glb',
    logo:      '/static/models/logo.glb',
    posters:   '/static/models/posters.glb',
    moonLamp:  '/static/models/moon_lamp.glb',
  };

  const FORCE_CUTSCENE = !!localStorage.getItem('luna_force_cutscene');
  const FORCE_TUTORIAL = !!localStorage.getItem('luna_force_tutorial');
  if (FORCE_CUTSCENE) localStorage.removeItem('luna_force_cutscene');
  if (FORCE_TUTORIAL) localStorage.removeItem('luna_force_tutorial');
  const IS_FIRST = !localStorage.getItem('luna_tutorial_done') || FORCE_CUTSCENE || FORCE_TUTORIAL;

  /* ═══════════════════════ AUDIO ═══════════════════════ */
  class SFX {
    constructor () { this.ctx = null; this.g = null; }
    init () {
      try {
        this.ctx = new (AudioContext || webkitAudioContext)();
        this.g = this.ctx.createGain();
        this.g.gain.value = 0.7;
        this.g.connect(this.ctx.destination);
      } catch (_) {}
    }
    _osc (f, dur, type = 'sine', vol = 0.3, att = 0.02) {
      if (!this.ctx) return;
      const t = this.ctx.currentTime;
      const o = this.ctx.createOscillator(); o.type = type; o.frequency.value = f;
      const g = this.ctx.createGain();
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(vol, t + att);
      g.gain.exponentialRampToValueAtTime(0.001, t + dur);
      o.connect(g).connect(this.g); o.start(t); o.stop(t + dur);
    }
    drone (dur = 22) {
      if (!this.ctx) return;
      const t = this.ctx.currentTime;
      [55, 82.5, 110, 165].forEach((f, i) => {
        const o = this.ctx.createOscillator();
        o.type = i < 2 ? 'sine' : 'triangle'; o.frequency.value = f;
        o.frequency.linearRampToValueAtTime(f * 1.02, t + dur);
        const g = this.ctx.createGain();
        g.gain.setValueAtTime(0, t);
        g.gain.linearRampToValueAtTime(i < 2 ? 0.12 : 0.05, t + 3);
        g.gain.setValueAtTime(i < 2 ? 0.12 : 0.05, t + dur - 3);
        g.gain.linearRampToValueAtTime(0, t + dur);
        o.connect(g).connect(this.g); o.start(t); o.stop(t + dur);
      });
    }
    step (isLeft = true) {
      if (!this.ctx) return;
      const t = this.ctx.currentTime;
      /* Soft indoor footstep — thump + light tap */
      const dur = 0.18;
      const buf = this.ctx.createBuffer(1, this.ctx.sampleRate * dur, this.ctx.sampleRate);
      const d = buf.getChannelData(0);
      const baseF = isLeft ? 75 : 90;
      for (let i = 0; i < d.length; i++) {
        const p = i / d.length;
        const env = Math.exp(-p * 12) * 0.8;
        d[i] = (Math.sin(2 * Math.PI * baseF * p * dur) * 0.7 +
                (Math.random() * 2 - 1) * 0.3) * env;
      }
      const s = this.ctx.createBufferSource(); s.buffer = buf;
      const lp = this.ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = isLeft ? 250 : 300; lp.Q.value = 0.7;
      const g = this.ctx.createGain(); g.gain.setValueAtTime(0.35, t); g.gain.exponentialRampToValueAtTime(0.001, t + dur);
      const pan = this.ctx.createStereoPanner ? this.ctx.createStereoPanner() : null;
      if (pan) pan.pan.value = isLeft ? -0.15 : 0.15;
      let ch = s.connect(lp).connect(g);
      if (pan) ch.connect(pan).connect(this.g); else ch.connect(this.g);
      s.start(t); s.stop(t + dur + 0.02);
    }
    bleep () { this._osc(1200, 0.08, 'square', 0.15); setTimeout(() => this._osc(1600, 0.06, 'square', 0.12), 90); }
    glitch (dur = 0.4) {
      if (!this.ctx) return;
      const t = this.ctx.currentTime;
      const buf = this.ctx.createBuffer(2, this.ctx.sampleRate * dur, this.ctx.sampleRate);
      for (let ch = 0; ch < 2; ch++) { const d = buf.getChannelData(ch); for (let i = 0; i < d.length; i++) { const p = i / d.length; d[i] = (Math.random() * 2 - 1) * (0.7 + (Math.sin(p * 80) * 0.5 + Math.sin(p * 200) * 0.3) * 0.3) * (1 - p * 0.6); } }
      const s = this.ctx.createBufferSource(); s.buffer = buf;
      const bp = this.ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 2500; bp.Q.value = 1.5;
      const g = this.ctx.createGain(); g.gain.setValueAtTime(0.3, t); g.gain.linearRampToValueAtTime(0, t + dur);
      s.connect(bp).connect(g).connect(this.g); s.start(t); s.stop(t + dur);
      const o = this.ctx.createOscillator(); o.type = 'sine'; o.frequency.value = 40;
      const g2 = this.ctx.createGain(); g2.gain.setValueAtTime(0.2, t); g2.gain.exponentialRampToValueAtTime(0.001, t + 0.2);
      o.connect(g2).connect(this.g); o.start(t); o.stop(t + 0.25);
    }
    whoosh (dur = 0.6) {
      if (!this.ctx) return;
      const t = this.ctx.currentTime;
      const buf = this.ctx.createBuffer(1, this.ctx.sampleRate * dur, this.ctx.sampleRate);
      const d = buf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
      const s = this.ctx.createBufferSource(); s.buffer = buf;
      const bp = this.ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = 0.8;
      bp.frequency.setValueAtTime(150, t); bp.frequency.exponentialRampToValueAtTime(3000, t + dur * 0.6); bp.frequency.exponentialRampToValueAtTime(500, t + dur);
      const g = this.ctx.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.35, t + dur * 0.15); g.gain.linearRampToValueAtTime(0, t + dur);
      s.connect(bp).connect(g).connect(this.g); s.start(t); s.stop(t + dur);
    }
    chime (f = 880, dur = 0.4) { this._osc(f, dur, 'sine', 0.25); }
    step2 () { this.chime(580 + Math.random() * 280, 0.2); }
    celebrate () { [523, 659, 784, 1047].forEach((f, i) => setTimeout(() => this.chime(f, .35), i * 90)); }
    creak () { this._osc(60 + Math.random() * 30, 0.6, 'triangle', 0.06, 0.15); }
    destroy () { if (this.ctx?.state !== 'closed') this.ctx?.close().catch(() => {}); }
  }

  /* ═══════════════════════ 3-D DESK SCENE ═══════════════════════ */
  class DeskScene {
    constructor (cvs) { this.cvs = cvs; this.dead = false; this._loaded = {}; }

    async boot (onProgress, mode) {
      const T = window.THREE; if (!T) return false;
      this.T = T; this.clk = new T.Clock(); this.mode = mode;

      this.sc = new T.Scene();
      this.sc.background = new T.Color(0x050810);
      this.sc.fog = new T.FogExp2(0x060a18, 0.035);

      // Camera: top-down isometric for loading, first-person for cutscene
      this.cam = new T.PerspectiveCamera(50, innerWidth / innerHeight, 0.05, 40);
      this._zooming = false;
      if (mode === 'loading') {
        // Start further away for zoom-in effect
        this.cam.position.set(0.1, 3.2, 1.8);
        this.cam.lookAt(0.1, 0.75, -1.5);
      } else {
        this.cam.position.set(0, 1.6, 5.5);
        this.cam.lookAt(0, 1.2, 0);
      }

      this.rdr = new T.WebGLRenderer({ canvas: this.cvs, antialias: true, alpha: false });
      this.rdr.setSize(innerWidth, innerHeight);
      this.rdr.setPixelRatio(Math.min(devicePixelRatio, 2));
      this.rdr.toneMapping = T.ACESFilmicToneMapping;
      this.rdr.toneMappingExposure = 1.0;
      this.rdr.shadowMap.enabled = true;
      this.rdr.shadowMap.type = T.PCFSoftShadowMap;
      try { this.rdr.outputColorSpace = T.SRGBColorSpace; } catch (_) {}

      /* Lights */
      this.sc.add(new T.AmbientLight(0x2a3050, 0.6));

      const key = new T.DirectionalLight(0x8899cc, 1.0);
      key.position.set(-3, 5, 2); key.castShadow = true;
      key.shadow.mapSize.set(1024, 1024);
      key.shadow.camera.near = 0.5; key.shadow.camera.far = 15;
      key.shadow.camera.left = -4; key.shadow.camera.right = 4;
      key.shadow.camera.top = 4; key.shadow.camera.bottom = -2;
      this.sc.add(key);

      // Warm fill from lamp area
      const fill = new T.PointLight(0xffcc88, 0.5, 4);
      fill.position.set(0.8, 1.5, -1.5); this.sc.add(fill);

      // Phone screen glow
      this.pLight = new T.PointLight(0x6b8aff, 1.5, 3);
      this.pLight.position.set(0.15, 1.0, -1.5); this.sc.add(this.pLight);

      // Back LED glow
      this._ledGlow = new T.PointLight(0x6b8aff, 0.3, 3);
      this._ledGlow.position.set(0, 0.85, -2.0); this.sc.add(this._ledGlow);

      if (onProgress) onProgress(10);

      // Procedural room (walls, floor, ceiling)
      this._buildRoom(T);
      if (onProgress) onProgress(20);

      // Load GLTFLoader then all models
      const loaderReady = await this._loadGLTFLoader(T);
      if (!loaderReady) {
        console.warn('GLTFLoader unavailable');
        return false;
      }
      if (onProgress) onProgress(30);

      await this._loadAllModels(T, onProgress);
      if (onProgress) onProgress(90);

      this._dust(T);
      if (onProgress) onProgress(95);

      this._onR = () => {
        if (this.dead) return;
        this.cam.aspect = innerWidth / innerHeight;
        this.cam.updateProjectionMatrix();
        this.rdr.setSize(innerWidth, innerHeight);
      };
      addEventListener('resize', this._onR);
      return true;
    }

    /* Basic room shell (procedural) */
    _buildRoom (T) {
      const g = new T.Group(); g.name = 'room';
      const Phys = (c, r = .3, m = .7) => new T.MeshPhysicalMaterial({ color: c, roughness: r, metalness: m });
      const Std  = (c, r = .85, m = 0)  => new T.MeshStandardMaterial({ color: c, roughness: r, metalness: m });

      // Floor
      const fl = new T.Mesh(new T.PlaneGeometry(8, 8),
        new T.MeshPhysicalMaterial({ color: 0x1a150e, roughness: 0.55, metalness: 0.04, clearcoat: 0.15 }));
      fl.rotation.x = -Math.PI / 2; fl.receiveShadow = true; g.add(fl);
      // Floor grooves
      for (let i = -10; i <= 10; i++) {
        const gr = new T.Mesh(new T.BoxGeometry(7.8, .001, .005),
          new T.MeshBasicMaterial({ color: 0x070510, transparent: true, opacity: .4 }));
        gr.rotation.x = -Math.PI / 2; gr.position.set(0, .001, i * .28); g.add(gr);
      }

      // Walls
      const wMat = new T.MeshPhysicalMaterial({ color: 0x0e0c1c, roughness: 0.88, metalness: 0.02 });
      const bw = new T.Mesh(new T.PlaneGeometry(8, 3.5), wMat);
      bw.position.set(0, 1.75, -4); bw.receiveShadow = true; g.add(bw);
      const lw = new T.Mesh(new T.PlaneGeometry(8, 3.5), wMat.clone());
      lw.rotation.y = Math.PI / 2; lw.position.set(-4, 1.75, 0); lw.receiveShadow = true; g.add(lw);
      const rw = new T.Mesh(new T.PlaneGeometry(8, 3.5), wMat.clone());
      rw.rotation.y = -Math.PI / 2; rw.position.set(4, 1.75, 0); rw.receiveShadow = true; g.add(rw);
      // Ceiling
      const cw = new T.Mesh(new T.PlaneGeometry(8, 8), Std(0x090818, .95));
      cw.rotation.x = Math.PI / 2; cw.position.set(0, 3.5, 0); g.add(cw);

      // Baseboards
      const bMat = Phys(0x0a0818, .6, .1);
      [[-4, .06, 0, 8, Math.PI / 2], [0, .06, -3.99, 8, 0], [4, .06, 0, 8, -Math.PI / 2]].forEach(
        ([x, y, z, w, ry]) => {
          const b = new T.Mesh(new T.BoxGeometry(w, .12, .018), bMat);
          b.position.set(x, y, z); b.rotation.y = ry; g.add(b);
        }
      );

      // Window (left wall)
      const frM = Phys(0x303848, .35, .55);
      const wf = new T.Mesh(new T.BoxGeometry(.08, 1.7, 1.5), frM);
      wf.position.set(-3.96, 2, -1); wf.castShadow = true; g.add(wf);
      const wfBar = new T.Mesh(new T.BoxGeometry(.09, .03, 1.42), frM);
      wfBar.position.set(-3.96, 2, -1); g.add(wfBar);
      const gl = new T.Mesh(new T.PlaneGeometry(1.36, 1.58),
        new T.MeshPhysicalMaterial({ color: 0x0c1525, roughness: 0.03, metalness: 0.1, transmission: 0.35, transparent: true, opacity: 0.3, clearcoat: 1 }));
      gl.rotation.y = Math.PI / 2; gl.position.set(-3.92, 2, -1); g.add(gl);
      const sky = new T.Mesh(new T.PlaneGeometry(1.4, 1.6), new T.MeshBasicMaterial({ color: 0x060d1c }));
      sky.rotation.y = Math.PI / 2; sky.position.set(-3.99, 2, -1); g.add(sky);
      const moonS = new T.Mesh(new T.CircleGeometry(.08, 20), new T.MeshBasicMaterial({ color: 0xd4dfff, transparent: true, opacity: 0.4 }));
      moonS.rotation.y = Math.PI / 2; moonS.position.set(-3.98, 2.45, -1.3); g.add(moonS);

      // LED strip on wall
      const led = new T.Mesh(new T.PlaneGeometry(2.0, .012), new T.MeshBasicMaterial({ color: 0x6b8aff, transparent: true, opacity: 0.7 }));
      led.position.set(0, .78, -3.98); g.add(led); this._led = led;

      // Ceiling light
      const fixM = Phys(0x222230, .3, .65);
      const fixPl = new T.Mesh(new T.CylinderGeometry(.16, .16, .012, 20), fixM);
      fixPl.position.set(0, 3.49, -1); g.add(fixPl);
      const cord = new T.Mesh(new T.CylinderGeometry(.004, .004, .5, 6), Phys(0x333340, .4, .5));
      cord.position.set(0, 3.25, -1); g.add(cord);
      this._bulb = new T.Mesh(new T.SphereGeometry(.028, 14, 14), new T.MeshBasicMaterial({ color: 0xffe4c4, transparent: true, opacity: .25 }));
      this._bulb.position.set(0, 3.0, -1); g.add(this._bulb);

      this.sc.add(g);
    }

    /* Load GLTFLoader script */
    _loadGLTFLoader (T) {
      if (T.GLTFLoader) return Promise.resolve(true);
      return new Promise(r => {
        const s = document.createElement('script');
        s.src = `${LOADER_CDN}/examples/js/loaders/GLTFLoader.js`;
        s.onload = () => r(!!T.GLTFLoader);
        s.onerror = () => r(false);
        document.head.appendChild(s);
      });
    }

    /* Load a single GLB, returns scene or null */
    _loadGLB (T, url) {
      return new Promise(r => {
        new T.GLTFLoader().load(url,
          gltf => r(gltf.scene),
          undefined,
          err => { console.warn('GLB load fail:', url, err); r(null); }
        );
      });
    }

    /* Load all models and position them */
    async _loadAllModels (T, onP) {
      // Table
      const table = await this._loadGLB(T, MODELS.table);
      if (table) {
        this._autoPlace(T, table, { targetH: 0.75, y0: 0, x: 0, z: -1.55 });
        table.traverse(c => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
        this.sc.add(table); this._loaded.table = table;
      }
      if (onP) onP(50);

      // Phone
      const phone = await this._loadGLB(T, MODELS.phone);
      if (phone) {
        // Scale phone to ~18cm
        const box = new T.Box3().setFromObject(phone);
        const sz = box.getSize(new T.Vector3());
        const maxD = Math.max(sz.x, sz.y, sz.z);
        const s = 0.18 / maxD; phone.scale.set(s, s, s);

        // Check if standing (Y tallest) → lay flat
        const box2 = new T.Box3().setFromObject(phone);
        const sz2 = box2.getSize(new T.Vector3());
        if (sz2.y > sz2.x * 1.3 && sz2.y > sz2.z * 1.3) {
          phone.rotation.x = -Math.PI / 2;
        }

        // Get desk surface height
        const deskY = this._loaded.table ? this._getTopY(T, this._loaded.table) : 0.77;

        // Place on desk
        const box3 = new T.Box3().setFromObject(phone);
        phone.position.y = deskY - box3.min.y + 0.002;
        phone.position.x = 0.15;
        phone.position.z = -1.5;
        phone.rotation.z = 0.05;

        phone.traverse(c => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
        this.sc.add(phone); this._loaded.phone = phone;

        // Find phone screen bounds for HTML overlay positioning
        this._findPhoneScreen(T, phone, deskY);
      }
      if (onP) onP(65);

      // Lamp
      const lamp = await this._loadGLB(T, MODELS.lamp);
      if (lamp) {
        const deskY = this._loaded.table ? this._getTopY(T, this._loaded.table) : 0.77;
        const box = new T.Box3().setFromObject(lamp);
        const sz = box.getSize(new T.Vector3());
        const maxD = Math.max(sz.x, sz.y, sz.z);
        // Lamp ~40cm tall
        const s = 0.40 / maxD; lamp.scale.set(s, s, s);
        const box2 = new T.Box3().setFromObject(lamp);
        lamp.position.y = deskY - box2.min.y + 0.002;
        lamp.position.x = 0.75;
        lamp.position.z = -1.75;
        lamp.traverse(c => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
        this.sc.add(lamp); this._loaded.lamp = lamp;
      }
      if (onP) onP(75);

      // Laptop
      const laptop = await this._loadGLB(T, MODELS.laptop);
      if (laptop) {
        const deskY = this._loaded.table ? this._getTopY(T, this._loaded.table) : 0.77;
        const box = new T.Box3().setFromObject(laptop);
        const sz = box.getSize(new T.Vector3());
        const maxD = Math.max(sz.x, sz.y, sz.z);
        const s = 0.35 / maxD; laptop.scale.set(s, s, s);
        const box2 = new T.Box3().setFromObject(laptop);
        laptop.position.y = deskY - box2.min.y + 0.002;
        laptop.position.x = -0.35;
        laptop.position.z = -1.7;
        laptop.traverse(c => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
        this.sc.add(laptop); this._loaded.laptop = laptop;
      }
      if (onP) onP(78);

      // Paper on desk
      const paper = await this._loadGLB(T, MODELS.paper);
      if (paper) {
        const deskY = this._loaded.table ? this._getTopY(T, this._loaded.table) : 0.77;
        const box = new T.Box3().setFromObject(paper);
        const sz = box.getSize(new T.Vector3());
        const maxD = Math.max(sz.x, sz.y, sz.z);
        const s = 0.22 / maxD; paper.scale.set(s, s, s);
        const box2 = new T.Box3().setFromObject(paper);
        paper.position.y = deskY - box2.min.y + 0.001;
        paper.position.x = -0.55;
        paper.position.z = -1.35;
        paper.rotation.y = 0.15;
        paper.traverse(c => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
        this.sc.add(paper); this._loaded.paper = paper;
      }

      // Logo on center of back wall (rotated to face viewer)
      const logo = await this._loadGLB(T, MODELS.logo);
      if (logo) {
        const box0 = new T.Box3().setFromObject(logo);
        const sz0 = box0.getSize(new T.Vector3());
        const maxD = Math.max(sz0.x, sz0.y, sz0.z);
        const s = 0.45 / maxD; logo.scale.set(s, s, s);
        logo.rotation.y = Math.PI;           // face +Z toward viewer
        logo.updateMatrixWorld(true);
        const box2 = new T.Box3().setFromObject(logo);
        const ctr = box2.getCenter(new T.Vector3());
        logo.position.x += (0 - ctr.x);     // center horizontally
        logo.position.y += (2.2 - ctr.y);   // wall height
        logo.position.z += (-3.95 - box2.min.z); // flush with wall
        logo.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
        this.sc.add(logo); this._loaded.logo = logo;
        // Logo spotlight
        const logoSpot = new T.SpotLight(0x6b8aff, 0.6, 3, Math.PI / 6, 0.5);
        logoSpot.position.set(0, 2.9, -3.5);
        logoSpot.target.position.set(0, 2.2, -3.96);
        this.sc.add(logoSpot); this.sc.add(logoSpot.target);
      }
      if (onP) onP(82);

      // Random poster on back wall (right of logo, rotated to face viewer)
      const postersRoot = await this._loadGLB(T, MODELS.posters);
      if (postersRoot) {
        const children = [];
        postersRoot.traverse(c => { if (c.isMesh) children.push(c); });
        if (children.length > 0) {
          const pick = children[Math.floor(Math.random() * children.length)];
          const poster = pick.clone();
          poster.position.set(0, 0, 0); poster.rotation.set(0, 0, 0);
          const tmpG = new T.Group(); tmpG.add(poster);
          // Scale
          const box0 = new T.Box3().setFromObject(tmpG);
          const sz0 = box0.getSize(new T.Vector3());
          const maxD = Math.max(sz0.x, sz0.y, sz0.z);
          const s = 0.50 / maxD; tmpG.scale.set(s, s, s);
          tmpG.rotation.y = Math.PI;            // face +Z toward viewer
          tmpG.updateMatrixWorld(true);
          const box2 = new T.Box3().setFromObject(tmpG);
          const ctr = box2.getCenter(new T.Vector3());
          tmpG.position.x += (0.8 - ctr.x);    // right of logo
          tmpG.position.y += (2.1 - ctr.y);    // wall height
          tmpG.position.z += (-3.95 - box2.min.z); // flush with wall
          tmpG.traverse(c => { if (c.isMesh) c.castShadow = true; });
          this.sc.add(tmpG); this._loaded.poster = tmpG;
        }
      }

      // Moon lamp on ceiling
      const moonLamp = await this._loadGLB(T, MODELS.moonLamp);
      if (moonLamp) {
        const box = new T.Box3().setFromObject(moonLamp);
        const sz = box.getSize(new T.Vector3());
        const maxD = Math.max(sz.x, sz.y, sz.z);
        const s = 0.35 / maxD; moonLamp.scale.set(s, s, s);
        const box2 = new T.Box3().setFromObject(moonLamp);
        // Hang from ceiling (y = 3.5)
        moonLamp.position.set(0, 3.48 - box2.max.y, -1);
        moonLamp.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
        this.sc.add(moonLamp); this._loaded.moonLamp = moonLamp;
        // Warm glow from moon lamp — starts dark, lit by approach trigger
        const moonGlow = new T.PointLight(0xffe4c4, 0, 4);
        moonGlow.position.set(0, 3.2, -1);
        this.sc.add(moonGlow);
        this._moonGlow = moonGlow;
      }
      if (onP) onP(88);
    }

    /* Get the highest Y point of a model (desk surface) */
    _getTopY (T, model) {
      const box = new T.Box3().setFromObject(model);
      return box.max.y;
    }

    /* Auto-place a model: scale to targetH, set position */
    _autoPlace (T, model, { targetH, y0 = 0, x = 0, z = 0 }) {
      const box = new T.Box3().setFromObject(model);
      const sz = box.getSize(new T.Vector3());
      const s = targetH / sz.y; model.scale.set(s, s, s);
      const box2 = new T.Box3().setFromObject(model);
      model.position.set(x, y0 - box2.min.y, z);
    }

    /* Find phone screen area for overlay */
    _findPhoneScreen (T, phoneModel, deskY) {
      // Get phone bounding box in world coords
      const box = new T.Box3().setFromObject(phoneModel);
      this._phoneBox = box;
      this._phoneDeskY = deskY;

      // Store center and size for overlay positioning
      const center = box.getCenter(new T.Vector3());
      const size = box.getSize(new T.Vector3());
      this._phoneCenter = center;
      this._phoneSize = size;
    }

    /* Get phone screen position projected to screen coords */
    getPhoneScreenRect () {
      if (!this._phoneCenter || !this.cam) return null;
      const T = this.T;

      // Phone screen center (slightly above phone center)
      const c = this._phoneCenter.clone();

      // Project to screen
      const v = c.clone().project(this.cam);
      const hw = innerWidth / 2, hh = innerHeight / 2;
      const cx = v.x * hw + hw;
      const cy = -v.y * hh + hh;

      // Estimate screen size based on phone dimensions projected
      const sz = this._phoneSize;
      // Get corners of the phone
      const box = this._phoneBox;
      const tl = new T.Vector3(box.min.x, box.max.y, box.min.z).project(this.cam);
      const br = new T.Vector3(box.max.x, box.min.y, box.max.z).project(this.cam);

      const x1 = tl.x * hw + hw, y1 = -tl.y * hh + hh;
      const x2 = br.x * hw + hw, y2 = -br.y * hh + hh;

      const w = Math.abs(x2 - x1);
      const h = Math.abs(y2 - y1);

      return { cx, cy, w: Math.max(w, 40), h: Math.max(h, 60), x: Math.min(x1, x2), y: Math.min(y1, y2) };
    }

    /* Dust particles */
    _dust (T) {
      const n = 100, pos = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        pos[i * 3]     = (Math.random() - .5) * 5;
        pos[i * 3 + 1] = Math.random() * 3;
        pos[i * 3 + 2] = (Math.random() - .5) * 5;
      }
      const geo = new T.BufferGeometry();
      geo.setAttribute('position', new T.BufferAttribute(pos, 3));
      this._du = new T.Points(geo, new T.PointsMaterial({
        size: .014, color: 0xffffff, transparent: true, opacity: .12,
        blending: T.AdditiveBlending, sizeAttenuation: true
      }));
      this.sc.add(this._du);
    }

    /* Animation loop */
    run () {
      if (this.dead) return;
      this._af = requestAnimationFrame(() => this.run());
      const t = this.clk.getElapsedTime();

      // Phone glow pulse
      if (this.pLight) this.pLight.intensity = 1.3 + Math.sin(t * 2.5) * 0.25;
      // LED color cycle
      if (this._led) {
        const hue = (t * .05) % 1 * .15 + .6;
        this._led.material.color.setHSL(hue, .8, .5);
        if (this._ledGlow) this._ledGlow.color.setHSL(hue, .7, .45);
      }
      if (this._bulb) this._bulb.material.opacity = .22 + Math.sin(t * 2.2) * .04;

      // Dust float
      if (this._du) {
        const a = this._du.geometry.attributes.position.array;
        for (let i = 0; i < a.length; i += 3) {
          a[i + 1] += Math.sin(t * .35 + i) * .0003;
          a[i]     += Math.cos(t * .2 + i * .5) * .0002;
        }
        this._du.geometry.attributes.position.needsUpdate = true;
      }

      // Gentle camera sway in loading mode (only when not zooming)
      if (this.mode === 'loading' && !this._zooming) {
        this.cam.position.x += Math.sin(t * 0.3) * 0.0005;
        this.cam.position.y += Math.sin(t * 0.2) * 0.0003;
        this.cam.lookAt(0.1, 0.75, -1.5);
      }

      /* Update phone screen texture */
      if (this._phoneScreen) this._phoneScreen.update();

      this.rdr.render(this.sc, this.cam);
    }

    moveCam (tp, tl, dur, ease = 'easeInOut') {
      return new Promise(r => {
        const sp = this.cam.position.clone();
        const sl = new this.T.Vector3();
        this.cam.getWorldDirection(sl); sl.multiplyScalar(5).add(sp);
        const s = performance.now();
        const go = () => {
          if (this.dead) { r(); return; }
          let p = Math.min((performance.now() - s) / (dur * 1000), 1);
          if (ease === 'easeInOut') p = p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
          else if (ease === 'easeOut') p = 1 - Math.pow(1 - p, 3);
          else if (ease === 'easeIn') p = p * p * p;
          this.cam.position.lerpVectors(sp, tp, p);
          this.cam.lookAt(new this.T.Vector3().lerpVectors(sl, tl, p));
          if (p < 1) requestAnimationFrame(go); else r();
        }; go();
      });
    }

    kill () {
      this.dead = true;
      if (this._af) cancelAnimationFrame(this._af);
      removeEventListener('resize', this._onR);
      if (this.rdr) { this.rdr.dispose(); this.rdr.forceContextLoss(); }
    }
  }

  /* ═══════════════════════ PHONE SCREEN 3D ═══════════════════════ */
  /* Renders content directly onto the phone surface as a 3D canvas texture */
  class PhoneScreen3D {
    constructor (scene3d) {
      this.s3 = scene3d;
      const T = scene3d.T;
      if (!scene3d._phoneBox) { this.mesh = null; return; }

      const box = scene3d._phoneBox;
      const center = scene3d._phoneCenter;
      const size = scene3d._phoneSize;

      /* Offscreen canvas — phone-like resolution */
      this.W = 360; this.H = 780;
      this.cvs = document.createElement('canvas');
      this.cvs.width = this.W; this.cvs.height = this.H;
      this.ctx = this.cvs.getContext('2d');

      /* Texture */
      this.tex = new T.CanvasTexture(this.cvs);
      this.tex.minFilter = T.LinearFilter;
      this.tex.magFilter = T.LinearFilter;

      /* Screen fills entire phone face (thin bezels) */
      const screenW = size.x * 0.92;
      const screenH = size.z * 0.94;

      /* Plane sitting on top of phone surface */
      const geo = new T.PlaneGeometry(screenW, screenH);
      const mat = new T.MeshBasicMaterial({ map: this.tex, toneMapped: false });
      this.mesh = new T.Mesh(geo, mat);
      this.mesh.position.set(center.x, box.max.y + 0.001, center.z);
      this.mesh.rotation.x = -Math.PI / 2;         // face up
      this.mesh.renderOrder = 1;
      scene3d.sc.add(this.mesh);

      /* Screen glow plane (slightly larger, additive) */
      const glowG = new T.PlaneGeometry(screenW * 1.3, screenH * 1.3);
      const glowM = new T.MeshBasicMaterial({
        color: 0x6b8aff, transparent: true, opacity: 0.06,
        blending: T.AdditiveBlending, depthWrite: false
      });
      this._glow = new T.Mesh(glowG, glowM);
      this._glow.position.copy(this.mesh.position);
      this._glow.position.y -= 0.001;
      this._glow.rotation.x = -Math.PI / 2;
      scene3d.sc.add(this._glow);

      this._mode = null;
      this._t0 = performance.now();
      this._logoImg = null;
      this._gifImg = null;
      this._loadImages();
    }

    _loadImages () {
      this._logoImg = new Image();
      this._logoImg.crossOrigin = 'anonymous';
      this._logoImg.src = LOGO;
      this._gifImg = new Image();
      this._gifImg.crossOrigin = 'anonymous';
      this._gifImg.src = LOADING_GIF;
    }

    showLoading () { this._mode = 'loading'; }
    showSite ()    { this._mode = 'site'; this._drawSite(); this.tex.needsUpdate = true; }
    showGlitch ()  { this._mode = 'glitch'; this._glitchT0 = performance.now(); }

    /* Called every frame from DeskScene.run() */
    update () {
      if (!this.mesh) return;
      if (this._mode === 'loading') {
        this._drawLoading();
        this.tex.needsUpdate = true;
      }
      if (this._mode === 'glitch') {
        this._drawGlitch();
        this.tex.needsUpdate = true;
      }
      /* Glow pulse */
      if (this._glow) {
        const t = (performance.now() - this._t0) / 1000;
        this._glow.material.opacity = 0.04 + Math.sin(t * 2) * 0.02;
      }
    }

    /* ── Phone glitch effect ── */
    _drawGlitch () {
      const ctx = this.ctx, W = this.W, H = this.H;
      const t = (performance.now() - (this._glitchT0 || this._t0)) / 1000;

      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);

      /* Scan lines */
      for (let y = 0; y < H; y += 3) {
        if (Math.random() > 0.65) {
          ctx.fillStyle = `rgba(107,138,255,${Math.random() * 0.12})`;
          ctx.fillRect(0, y, W, 2);
        }
      }

      /* Glitch bands */
      const bands = 1 + Math.floor(Math.random() * 3);
      for (let b = 0; b < bands; b++) {
        if (Math.random() > 0.6) {
          const by = Math.random() * H, bh = 5 + Math.random() * 40;
          const shift = (Math.random() - 0.5) * 30;
          ctx.fillStyle = `rgba(107,138,255,${0.05 + Math.random() * 0.2})`;
          ctx.fillRect(shift, by, W, bh);
        }
      }

      /* Random color blocks */
      if (Math.random() > 0.8) {
        const bx = Math.random() * W, by = Math.random() * H;
        const bw = 20 + Math.random() * 80, bh = 5 + Math.random() * 20;
        ctx.fillStyle = Math.random() > 0.5 ? 'rgba(255,50,80,0.15)' : 'rgba(80,255,180,0.12)';
        ctx.fillRect(bx, by, bw, bh);
      }

      /* Flash */
      if (Math.random() > 0.9) {
        ctx.fillStyle = `rgba(107,138,255,${0.2 + Math.random() * 0.3})`;
        ctx.fillRect(0, 0, W, H);
      }

      /* LUNA text flicker */
      if (Math.sin(t * 12) > 0.2) {
        ctx.fillStyle = `rgba(107,138,255,${0.3 + Math.random() * 0.5})`;
        ctx.font = 'bold 26px -apple-system, system-ui, sans-serif';
        ctx.textAlign = 'center';
        const ox = (Math.random() - 0.5) * 10, oy = (Math.random() - 0.5) * 10;
        ctx.fillText('LUNA', W / 2 + ox, H / 2 + oy);
      }

      this._drawNotch(ctx, W);
    }

    /* ── Draw camera notch at top ── */
    _drawNotch (ctx, W) {
      const nW = 110, nH = 28, nR = 14;
      const nx = (W - nW) / 2;
      ctx.fillStyle = '#000';
      ctx.beginPath();
      ctx.moveTo(nx, 0);
      ctx.lineTo(nx, nH - nR);
      ctx.quadraticCurveTo(nx, nH, nx + nR, nH);
      ctx.lineTo(nx + nW - nR, nH);
      ctx.quadraticCurveTo(nx + nW, nH, nx + nW, nH - nR);
      ctx.lineTo(nx + nW, 0);
      ctx.fill();
      /* Camera dot */
      ctx.beginPath();
      ctx.arc(W / 2 + 20, nH / 2, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#1a1a2e'; ctx.fill();
      ctx.beginPath();
      ctx.arc(W / 2 + 20, nH / 2, 2, 0, Math.PI * 2);
      ctx.fillStyle = '#0d0d1a'; ctx.fill();
    }

    /* ── Loading screen ── */
    _drawLoading () {
      const ctx = this.ctx, W = this.W, H = this.H;
      const t = (performance.now() - this._t0) / 1000;

      /* BG gradient */
      const grad = ctx.createLinearGradient(0, 0, 0, H);
      grad.addColorStop(0, '#0e1225'); grad.addColorStop(1, '#070a14');
      ctx.fillStyle = grad; ctx.fillRect(0, 0, W, H);

      /* Screen rounded corners */
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(0, 0, W, H, 18);
      ctx.clip();

      /* Subtle radial glow */
      const rg = ctx.createRadialGradient(W / 2, H * 0.38, 0, W / 2, H * 0.38, 200);
      rg.addColorStop(0, 'rgba(107,138,255,0.08)'); rg.addColorStop(1, 'transparent');
      ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);

      /* Logo */
      const ls = 80, lx = (W - ls) / 2, ly = H * 0.30;
      const pulse = 1 + Math.sin(t * 2.5) * 0.04;
      if (this._logoImg?.complete) {
        ctx.save();
        ctx.translate(lx + ls / 2, ly + ls / 2);
        ctx.scale(pulse, pulse);
        ctx.beginPath();
        ctx.roundRect(-ls / 2, -ls / 2, ls, ls, 18);
        ctx.clip();
        ctx.drawImage(this._logoImg, -ls / 2, -ls / 2, ls, ls);
        ctx.restore();
        /* glow ring */
        ctx.save();
        ctx.shadowColor = 'rgba(107,138,255,0.35)';
        ctx.shadowBlur = 28;
        ctx.beginPath();
        ctx.roundRect(lx, ly, ls, ls, 18);
        ctx.strokeStyle = 'rgba(107,138,255,0.12)';
        ctx.lineWidth = 1.5; ctx.stroke();
        ctx.restore();
      }

      /* App name */
      ctx.fillStyle = '#e0e6ff';
      ctx.font = 'bold 22px -apple-system, "SF Pro Display", system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Luna Gifts', W / 2, ly + ls + 38);

      /* Animated dots */
      const dotY = ly + ls + 68;
      for (let i = 0; i < 3; i++) {
        const phase = Math.sin((t * 3 + i * 0.8) * Math.PI) * 0.5 + 0.5;
        const r = 4 + phase * 2.5;
        ctx.beginPath();
        ctx.arc(W / 2 + (i - 1) * 20, dotY, r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(107,138,255,${0.25 + phase * 0.75})`;
        ctx.fill();
      }

      /* Loading gif */
      if (this._gifImg?.complete) {
        const gs = 52;
        ctx.drawImage(this._gifImg, (W - gs) / 2, dotY + 36, gs, gs);
      }

      /* Spinner ring */
      const sY = dotY + 110, sR = 14;
      ctx.save();
      ctx.translate(W / 2, sY);
      ctx.rotate(t * 4);
      ctx.beginPath();
      ctx.arc(0, 0, sR, 0, Math.PI * 1.3);
      ctx.strokeStyle = 'rgba(107,138,255,0.6)';
      ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.stroke();
      ctx.restore();

      /* Notch */
      ctx.restore();
      this._drawNotch(ctx, W);
    }

    /* ── Site content (drawn once) ── */
    _drawSite () {
      const ctx = this.ctx, W = this.W, H = this.H;

      ctx.fillStyle = '#0a0e17'; ctx.fillRect(0, 0, W, H);

      /* Rounded screen */
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(0, 0, W, H, 18);
      ctx.clip();

      ctx.fillStyle = '#0a0e17'; ctx.fillRect(0, 0, W, H);

      /* Status bar (below notch) */
      const notchH = 30;
      ctx.fillStyle = 'rgba(255,255,255,0.35)';
      ctx.font = '600 12px -apple-system, system-ui, sans-serif';
      ctx.textAlign = 'left';  ctx.fillText('9:41', 20, notchH + 16);
      ctx.textAlign = 'right'; ctx.fillText('100%', W - 20, notchH + 16);

      /* Header */
      const hY = notchH + 28;
      /* avatar */
      ctx.beginPath(); ctx.arc(38, hY + 20, 20, 0, Math.PI * 2);
      const ag = ctx.createLinearGradient(18, hY, 58, hY + 40);
      ag.addColorStop(0, 'rgba(107,138,255,0.25)'); ag.addColorStop(1, 'rgba(168,85,247,0.25)');
      ctx.fillStyle = ag; ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1; ctx.stroke();
      /* username + balance */
      ctx.fillStyle = '#f0f2f5';
      ctx.font = 'bold 16px -apple-system, system-ui, sans-serif';
      ctx.textAlign = 'left'; ctx.fillText('User', 68, hY + 16);
      ctx.fillStyle = '#ffd74a';
      ctx.font = 'bold 14px -apple-system, system-ui, sans-serif';
      ctx.fillText('★ 100', 68, hY + 36);
      /* plus btn */
      ctx.beginPath(); ctx.arc(W - 38, hY + 20, 17, 0, Math.PI * 2);
      ctx.fillStyle = '#6b8aff'; ctx.fill();
      ctx.fillStyle = '#fff'; ctx.font = 'bold 20px system-ui'; ctx.textAlign = 'center';
      ctx.fillText('+', W - 38, hY + 27);

      /* Section title */
      ctx.fillStyle = '#f0f2f5';
      ctx.font = 'bold 18px -apple-system, system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText('\uD83C\uDF81  Подарки', 20, hY + 80);

      /* Gift cards 2×3 */
      const gT = hY + 100, cW = (W - 56) / 2, cH = 130, gap = 12;
      const colors = ['#6b8aff', '#a855f7', '#34d87a', '#ffd74a', '#f472b6', '#e64c4c'];
      for (let r = 0; r < 3; r++) for (let c = 0; c < 2; c++) {
        const cx = 20 + c * (cW + gap), cy = gT + r * (cH + gap), cl = colors[r * 2 + c];
        ctx.beginPath(); ctx.roundRect(cx, cy, cW, cH, 14);
        ctx.fillStyle = 'rgba(255,255,255,0.03)'; ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.06)'; ctx.lineWidth = 1; ctx.stroke();
        /* icon placeholder */
        ctx.beginPath(); ctx.roundRect(cx + cW / 2 - 22, cy + 18, 44, 44, 12);
        ctx.fillStyle = cl + '20'; ctx.fill();
        /* price */
        ctx.fillStyle = '#ffd74a';
        ctx.font = 'bold 12px -apple-system, system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('★ ' + (50 + r * 30 + c * 15), cx + cW / 2, cy + cH - 16);
      }

      /* Nav bar */
      const nY = H - 62;
      ctx.fillStyle = 'rgba(255,255,255,0.03)'; ctx.fillRect(0, nY, W, 62);
      ctx.fillStyle = 'rgba(255,255,255,0.06)'; ctx.fillRect(0, nY, W, 1);
      const icons = ['\uD83C\uDFE0','\uD83C\uDF81','\uD83D\uDCE6','\uD83C\uDFAE','\uD83D\uDC64'];
      const labels = ['Главная','Подарки','Кейсы','Игры','Профиль'];
      const nW = W / icons.length;
      icons.forEach((ic, i) => {
        const nx2 = i * nW + nW / 2, active = i === 1;
        ctx.globalAlpha = active ? 1 : 0.3;
        ctx.font = '18px system-ui'; ctx.textAlign = 'center';
        ctx.fillStyle = '#fff'; ctx.fillText(ic, nx2, nY + 26);
        ctx.font = '9px -apple-system, system-ui, sans-serif';
        ctx.fillStyle = active ? '#6b8aff' : '#fff';
        ctx.fillText(labels[i], nx2, nY + 42);
        ctx.globalAlpha = 1;
      });

      ctx.restore();
      /* Notch on top */
      this._drawNotch(ctx, W);
    }

    destroy () {
      if (this.mesh) {
        this.s3.sc.remove(this.mesh);
        this.mesh.geometry.dispose();
        this.mesh.material.dispose();
        this.tex.dispose();
      }
      if (this._glow) {
        this.s3.sc.remove(this._glow);
        this._glow.geometry.dispose();
        this._glow.material.dispose();
      }
    }
  }

  /* ═══════════════════════ MAIN CONTROLLER ═══════════════════════ */
  class Cutscene {
    constructor () { this.ov = null; this.sfx = new SFX(); this.s3 = null; this.stop = false; }

    async go () {
      if (IS_FIRST) {
        await this._runFullCutscene();
      } else {
        // Only show 3D loading on first visit in session or page reload
        const nav = performance.getEntriesByType?.('navigation')?.[0];
        const isReload = nav ? nav.type === 'reload' : (performance.navigation?.type === 1);
        const csShown = sessionStorage.getItem('luna_cs_shown');
        if (!csShown || isReload) {
          sessionStorage.setItem('luna_cs_shown', '1');
          await this._runLoadingScreen();
        }
      }
    }

    /* ═══════ RETURN VISIT: 3D loading screen ═══════ */
    async _runLoadingScreen () {
      this._domLoading();
      const ok = await this._lib();
      if (!ok) { this._endLoading(); return; }

      this.s3 = new DeskScene(document.getElementById('cutsceneCanvas'));
      const booted = await this.s3.boot(p => this._loadProgLoading(p), 'loading');
      if (!booted) { this._endLoading(); return; }

      this.s3.run();

      // Render loading content on phone 3D surface
      this.phoneScr = new PhoneScreen3D(this.s3);
      this.s3._phoneScreen = this.phoneScr;
      this.phoneScr.showLoading();

      // 5-second zoom towards phone
      const T = window.THREE;
      this.s3._zooming = true;
      await this.s3.moveCam(
        new T.Vector3(0.15, 1.15, -0.8),   // end position: close to phone
        new T.Vector3(0.15, 0.80, -1.5),   // look at phone center
        5.0, 'easeInOut'
      );
      this.s3._zooming = false;

      // Wait for main page to be ready
      await this._waitForPage();

      // Show site UI on phone
      this.phoneScr.showSite();
      await this._w(1800);

      this._endLoading();
    }

    _domLoading () {
      const o = document.createElement('div');
      o.id = 'cutsceneOverlay';
      o.innerHTML = `
        <canvas id="cutsceneCanvas"></canvas>
        <div class="cs-vignette"></div>
        <div class="cs-load-text" id="csLoadText">
          <img src="${LOGO}" class="cs-lt-logo" alt="">
          <div class="cs-lt-name">Luna Gifts</div>
        </div>
      `;
      document.body.prepend(o);
      this.ov = o;
    }

    _loadProgLoading (p) {
      // Could show progress on overlay, for now just logs
    }

    async _waitForPage () {
      // Wait until main .container has some content
      return new Promise(r => {
        let checks = 0;
        const check = () => {
          checks++;
          const c = document.querySelector('.container');
          const hasContent = c && c.children.length > 1;
          if (hasContent || checks > 40) { r(); return; }
          setTimeout(check, 250);
        };
        check();
      });
    }

    _endLoading () {
      if (this.phoneScr) { this.phoneScr.destroy(); this.s3._phoneScreen = null; }
      if (this.s3) this.s3.kill();
      if (this.ov) {
        this.ov.classList.add('fade-out');
        setTimeout(() => this.ov?.remove(), 800);
      }
    }

    /* ═══════ FIRST VISIT: full cinematic ═══════ */
    async _runFullCutscene () {
      this._dom();
      this.sfx.init();
      this._showLoading();
      const ok = await this._lib();
      if (ok && !this.stop) {
        this.s3 = new DeskScene(document.getElementById('cutsceneCanvas'));
        const booted = await this.s3.boot(p => this._loadProg(p), 'cutscene');
        if (booted) {
          this._hideLoading();
          this.s3.run();
          await this._scene1();
          if (!this.stop) await this._scene2();
        } else {
          this._hideLoading();
          await this._fallback();
        }
      } else if (!this.stop) {
        this._hideLoading();
        await this._fallback();
      }
      if (!this.stop) await this._tut();
    }

    _dom () {
      const o = document.createElement('div');
      o.id = 'cutsceneOverlay';
      o.innerHTML = `
        <canvas id="cutsceneCanvas"></canvas>
        <div class="cs-vignette"></div>
        <div class="cs-letterbox cs-letterbox-top"></div>
        <div class="cs-letterbox cs-letterbox-bottom"></div>
        <div class="cs-text-layer" id="csTextLayer"></div>
        <div class="cs-loading-screen" id="csLoadingScreen">
          <div class="cs-load-inner">
            <img src="${LOGO}" class="cs-load-logo" alt="">
            <div class="cs-load-title">Luna Gifts</div>
            <div class="cs-load-bar-wrap"><div class="cs-load-bar" id="csLoadBar"></div></div>
            <div class="cs-load-status" id="csLoadStatus">Загрузка...</div>
          </div>
        </div>
        <div class="cs-glitch-layer" id="csGlitchLayer"></div>
        <div class="cs-flash" id="csFlash"></div>
        <div class="cs-tutorial" id="csTutorial"></div>
        <div class="cs-progress"><div class="cs-progress-bar" id="csProgressBar"></div></div>
        <div class="cs-tap-skip" id="csTapSkip">нажмите, чтобы пропустить</div>
      `;
      document.body.prepend(o);
      this.ov = o;
      document.getElementById('csTapSkip').addEventListener('click', () => this._skip());
    }

    _showLoading () { document.getElementById('csLoadingScreen')?.classList.add('visible'); }
    _hideLoading () {
      const ls = document.getElementById('csLoadingScreen');
      if (ls) { ls.classList.add('fade-out'); setTimeout(() => ls.remove(), 500); }
    }
    _loadProg (p) {
      const bar = document.getElementById('csLoadBar');
      const st  = document.getElementById('csLoadStatus');
      if (bar) bar.style.width = p + '%';
      if (st) {
        if (p < 20) st.textContent = 'Строим комнату...';
        else if (p < 50) st.textContent = 'Загружаем модели...';
        else if (p < 85) st.textContent = 'Расставляем предметы...';
        else if (p < 95) st.textContent = 'Настраиваем свет...';
        else st.textContent = 'Готово!';
      }
    }
    _lib () {
      if (window.THREE) return Promise.resolve(true);
      return new Promise(r => {
        const s = document.createElement('script');
        s.src = `${CDN}/build/three.min.js`;
        s.onload = () => r(true); s.onerror = () => r(false);
        document.head.appendChild(s);
        setTimeout(() => r(!!window.THREE), 8000);
      });
    }

    /* ═══════ SCENE 1 — walk → desk → zoom ═══════ */
    async _scene1 () {
      this._prog(0);
      document.querySelectorAll('.cs-letterbox').forEach(b => b.classList.add('active'));
      this.sfx.drone(25);
      const T = window.THREE;

      /* Walk with head bob — reduced intensity */
      const walkDur = 5, wStart = performance.now();
      const startP = this.s3.cam.position.clone();
      const endP   = new T.Vector3(0.05, 1.6, 1.5);
      const startL = new T.Vector3(0, 1.2, 0);
      const endL   = new T.Vector3(0.12, 1.0, -1.0);
      let stepCount = 0, lastStep = 0;
      const stepInterval = 550;
      let triggered = false;

      await new Promise(resolve => {
        const go = () => {
          if (this.stop || this.s3.dead) { resolve(); return; }
          const elapsed = performance.now() - wStart;
          let p = Math.min(elapsed / (walkDur * 1000), 1);
          const ep = p < 0.12 ? (p / 0.12) ** 2 * 0.12 :
                     p > 0.88 ? 0.88 + (1 - (1 - (p - 0.88) / 0.12) ** 2) * 0.12 : p;
          const walkCycle = elapsed / stepInterval * Math.PI;
          const bobAmt = Math.min(p * 4, 1) * (1 - Math.max(0, (p - 0.88) * 8.33));
          this.s3.cam.position.lerpVectors(startP, endP, ep);
          this.s3.cam.position.y += Math.abs(Math.sin(walkCycle)) * 0.018 * bobAmt + Math.sin(elapsed * 0.0018) * 0.002;
          this.s3.cam.position.x += Math.sin(walkCycle * 0.5) * 0.008 * bobAmt;
          this.s3.cam.rotation.z = Math.sin(walkCycle * 0.5) * 0.005 * bobAmt;
          this.s3.cam.lookAt(new T.Vector3().lerpVectors(startL, endL, ep));
          if (elapsed - lastStep > stepInterval && p > 0.04 && p < 0.9) {
            this.sfx.step(stepCount % 2 === 0); stepCount++; lastStep = elapsed;
          }

          /* === Approach trigger at 60% — phone glitches, moon lights up === */
          if (p > 0.6 && !triggered) {
            triggered = true;
            this.phoneScr = new PhoneScreen3D(this.s3);
            this.s3._phoneScreen = this.phoneScr;
            this.phoneScr.showGlitch();
            this.sfx.glitch(0.3);
            // Animate moon lamp glow on
            if (this.s3._moonGlow) {
              const mg = this.s3._moonGlow;
              const gt0 = performance.now();
              const animMoon = () => {
                const gp = Math.min((performance.now() - gt0) / 2500, 1);
                mg.intensity = gp * 0.5;
                if (this.s3._loaded.moonLamp) {
                  this.s3._loaded.moonLamp.traverse(c => {
                    if (c.isMesh && c.material) {
                      if (!c.material.emissive) c.material.emissive = new T.Color();
                      c.material.emissive.setHex(0xffe4c4);
                      c.material.emissiveIntensity = gp * 0.4;
                    }
                  });
                }
                if (gp < 1 && !this.stop) requestAnimationFrame(animMoon);
              }; animMoon();
            }
          }

          if (p < 1) requestAnimationFrame(go); else resolve();
        }; go();
      });
      if (this.stop) return;
      this._prog(20); this.sfx.creak();

      /* Tilt down to desk */
      await this._w(200); if (this.stop) return;
      await this.s3.moveCam(new T.Vector3(0.15, 1.35, -0.5), new T.Vector3(0.15, 0.78, -1.5), 2.0, 'easeOut');
      if (this.stop) return;

      this.sfx.bleep();
      if (this.s3.pLight) {
        const si = this.s3.pLight.intensity, t0 = performance.now();
        const gl = () => { const p2 = Math.min((performance.now() - t0) / 1500, 1); this.s3.pLight.intensity = si + p2; if (p2 < 1 && !this.stop) requestAnimationFrame(gl); }; gl();
      }
      await this._w(400); if (this.stop) return;

      // Switch phone from glitch to site content (or create if trigger missed)
      if (!this.phoneScr) {
        this.phoneScr = new PhoneScreen3D(this.s3);
        this.s3._phoneScreen = this.phoneScr;
      }
      this.phoneScr.showSite();

      const tl = document.getElementById('csTextLayer');
      tl.innerHTML = `<div class="cs-caption" id="c1"><span>Luna Gifts</span><div class="cs-caption-sub">МИР ПОДАРКОВ</div></div>`;
      requestAnimationFrame(() => document.getElementById('c1')?.classList.add('visible'));
      this._prog(35);
      await this._w(2500); if (this.stop) return;
      document.getElementById('c1')?.classList.add('out');
      await this._w(300); if (this.stop) return;

      /* Zoom into phone */
      this.sfx.whoosh(3);
      await this.s3.moveCam(new T.Vector3(0.15, 0.88, -1.28), new T.Vector3(0.15, 0.78, -1.5), 6.5, 'easeIn');
      if (this.stop) return;
      this._flash(); this._prog(55);
      await this._w(200);
    }

    /* ═══════ SCENE 2 — glitch → real page expand ═══════ */
    async _scene2 () {
      this._prog(58);
      if (this.phoneScr) { this.phoneScr.destroy(); this.s3._phoneScreen = null; }
      if (this.s3) { this.s3.kill(); const c = document.getElementById('cutsceneCanvas'); if (c) c.style.display = 'none'; }
      document.querySelectorAll('.cs-letterbox').forEach(b => b.classList.remove('active'));
      document.getElementById('csTextLayer').innerHTML = '';

      this.sfx.glitch(0.4);
      const gl = document.getElementById('csGlitchLayer');
      gl.classList.add('active'); this._prog(62);
      await this._w(300); if (this.stop) return;
      gl.classList.remove('active');
      await this._w(50);
      this.sfx.glitch(0.15); gl.classList.add('active');
      await this._w(120); if (this.stop) return;
      gl.classList.remove('active');
      await this._w(100); if (this.stop) return;

      this._showRealPage(); this.sfx.bleep(); this._prog(68);
      await this._w(1500); if (this.stop) return;

      this.sfx.whoosh(0.8); this._flash();
      document.getElementById('csRealFrame')?.classList.add('expand');
      this._prog(80);
      await this._w(1000); if (this.stop) return;
      document.getElementById('csRealOverlay')?.remove();
    }

    _showRealPage () {
      const overlay = document.createElement('div');
      overlay.className = 'cs-real-overlay'; overlay.id = 'csRealOverlay';
      const frame = document.createElement('div');
      frame.className = 'cs-real-frame'; frame.id = 'csRealFrame';
      const inner = document.createElement('div');
      inner.className = 'cs-real-inner';
      const container = document.querySelector('.container');
      const nav = document.querySelector('.bottom-nav');
      if (container) { const cc = container.cloneNode(true); cc.querySelectorAll('.loading,.modal-overlay').forEach(l => l.remove()); inner.appendChild(cc); }
      if (nav) { const nc = nav.cloneNode(true); nc.style.cssText = 'position:relative;bottom:auto;left:auto;right:auto;width:100%;'; inner.appendChild(nc); }
      frame.appendChild(inner); overlay.appendChild(frame); this.ov.appendChild(overlay);
      requestAnimationFrame(() => requestAnimationFrame(() => overlay.classList.add('visible')));
    }

    async _fallback () {
      this._prog(0); this.sfx.drone(8); this._particles();
      const tl = document.getElementById('csTextLayer');
      await this._w(400);
      tl.innerHTML = `<div class="cs-caption" id="c1"><span>Luna Gifts</span><div class="cs-caption-sub">МИР ПОДАРКОВ</div></div>`;
      requestAnimationFrame(() => document.getElementById('c1')?.classList.add('visible'));
      this.sfx.chime(440, 0.5); this._prog(30);
      await this._w(3000); if (this.stop) return;
      document.getElementById('c1')?.classList.add('out');
      await this._w(400);
      this.sfx.glitch(0.3);
      const gl = document.getElementById('csGlitchLayer'); gl.classList.add('active');
      await this._w(300); gl.classList.remove('active');
      this._prog(80); await this._w(300);
    }

    /* ═══════ Tutorial (first time only) ═══════ */
    async _tut () {
      this._prog(80);
      const tut = document.getElementById('csTutorial');
      tut.classList.add('visible');
      const ts = document.getElementById('csTapSkip'); if (ts) ts.style.display = 'none';

      const S = [
        { icon: LOGO, big: true, t: 'Добро пожаловать в Luna Gifts!', d: 'Это площадка, где ты зарабатываешь звёзды, открываешь кейсы и&nbsp;выигрываешь подарки Telegram', c: '#6b8aff' },
        { icon: STAR, t: 'Пополняй баланс', d: 'Stars через Telegram или TON через криптокошелёк — жми «+» рядом с балансом', c: '#ffd74a' },
        { icon: '/static/img/task.png', t: 'Выполняй задания', d: 'Подпишись на&nbsp;каналы, пригласи друзей — получай звёзды за&nbsp;каждое задание', c: '#34d87a' },
        { icon: '/static/img/games.png', t: 'Играй и выигрывай', d: 'Кейсы, скретчи и мини-игры — шанс выиграть редкие подарки и&nbsp;звёзды', c: '#a855f7' },
        { icon: '/static/img/gift.png', t: 'Выводи подарки', d: 'Подарки можно вывести прямо в&nbsp;Telegram — они придут в&nbsp;личные сообщения', c: '#f472b6' },
      ];

      let idx = 0;
      const show = i => {
        const s = S[i], last = i >= S.length - 1;
        tut.innerHTML = `
          <div class="cs-tut-wrap">
            <div class="cs-tut-card" id="tc">
              <div class="cs-tut-glow" style="background:radial-gradient(circle,${s.c}33,transparent 60%)"></div>
              <div class="cs-tut-icon-wrap">
                <img class="cs-tut-icon${s.big ? ' big' : ''}" src="${s.icon}" alt="">
              </div>
              <div class="cs-tut-title">${s.t}</div>
              <div class="cs-tut-text">${s.d}</div>
            </div>
            <div class="cs-tut-dots">${S.map((_, j) => `<div class="cs-tut-dot${j === i ? ' active' : ''}" style="${j === i ? `background:${s.c};box-shadow:0 0 10px ${s.c}66` : ''}"></div>`).join('')}</div>
            <div class="cs-tut-actions">
              <div class="cs-tut-counter" style="color:${s.c}88">${i + 1} / ${S.length}</div>
              <button class="cs-tut-btn" id="tn" style="background:linear-gradient(135deg,${s.c},${s.c}cc)">${last ? 'Начать! 🚀' : 'Далее →'}</button>
            </div>
          </div>`;
        requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById('tc')?.classList.add('visible')));
      };

      show(0); this.sfx.step2();

      return new Promise(r => {
        const nx = () => {
          idx++; this.sfx.step2();
          this._prog(80 + (idx / S.length) * 20);
          if (idx >= S.length) { this.sfx.celebrate(); this._end(); r(); return; }
          show(idx); wire();
        };
        const wire = () => { const b = document.getElementById('tn'); if (b) b.addEventListener('click', nx, { once: true }); };
        wire();
      });
    }

    _flash () {
      const f = document.getElementById('csFlash'); if (!f) return;
      f.classList.add('bang');
      setTimeout(() => { f.classList.remove('bang'); f.style.opacity = '0'; setTimeout(() => { f.style.opacity = ''; }, 400); }, 100);
    }
    _prog (p) { const b = document.getElementById('csProgressBar'); if (b) b.style.width = p + '%'; }
    _w (ms) { return new Promise(r => { this._t = setTimeout(r, ms); }); }
    _particles () {
      if (!this.ov) return;
      let h = '<div class="cs-particles">';
      for (let i = 0; i < 25; i++) {
        const c = ['', 'gold', 'green', 'purple'][i % 4];
        h += `<div class="cs-particle ${c}" style="left:${Math.random() * 100}%;width:${2 + Math.random() * 3}px;height:${2 + Math.random() * 3}px;animation-duration:${4 + Math.random() * 6}s;animation-delay:${Math.random() * 4}s"></div>`;
      }
      this.ov.insertAdjacentHTML('afterbegin', h + '</div>');
    }
    _skip () { this.stop = true; clearTimeout(this._t); this._end(); }
    _end () {
      localStorage.setItem('luna_tutorial_done', '1');
      if (this.phoneScr) this.phoneScr.destroy();
      if (this.s3) this.s3.kill();
      this.sfx.destroy();
      if (this.ov) { this.ov.classList.add('fade-out'); setTimeout(() => this.ov?.remove(), 800); }
    }
  }

  /* AUTO START */
  const c = new Cutscene();
  window._lunaCutscene = c;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => c.go());
  else c.go();

})();
