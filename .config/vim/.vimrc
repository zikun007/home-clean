"================= Basic =================
set nocompatible
syntax enable

set number
set ruler
set cmdheight=1
set showcmd
set history=1000

set mouse=a
set autowrite
set hidden

set noerrorbells
set novisualbell
set showmatch
set matchtime=2
set magic

" ================= Search =================
set hlsearch
set incsearch
set ignorecase
set smartcase

" ================= Indent =================
set expandtab
set tabstop=4
set softtabstop=4
set shiftwidth=4
set smarttab
set autoindent
set cindent
" smartindent 和 cindent 有重叠，这里保留 cindent 即可

" ================= Encoding =================
set encoding=utf-8
set fileencodings=utf-8,ucs-bom,gb18030,cp936,latin1
set langmenu=zh_CN.UTF-8
set helplang=cn,en
" termencoding 通常保持默认即可，不必强设

" ================= Clipboard =================
if has('unnamedplus')
    set clipboard+=unnamedplus
else
    set clipboard+=unnamed
endif

" ================= UI / Theme =================
set background=dark
if has('termguicolors')
    set termguicolors
endif

set cursorline
set nocursorcolumn

highlight Normal       ctermfg=252 ctermbg=NONE guifg=#d4d4d4 guibg=NONE
highlight LineNr       ctermfg=240 ctermbg=NONE guifg=#5c6370 guibg=NONE
highlight CursorLineNr ctermfg=220 ctermbg=NONE cterm=bold gui=bold guifg=#ffd75f guibg=NONE
highlight CursorLine   cterm=NONE ctermbg=236 gui=NONE guibg=#1f2330
highlight Visual       cterm=NONE ctermbg=60  gui=NONE guibg=#33467c
highlight Search       ctermfg=16  ctermbg=220 gui=NONE guifg=#111111 guibg=#ffd75f
highlight IncSearch    ctermfg=16  ctermbg=215 cterm=bold gui=bold guifg=#111111 guibg=#ffaf5f
highlight Pmenu        ctermfg=252 ctermbg=238 gui=NONE guifg=#d4d4d4 guibg=#2a2f3a
highlight PmenuSel     ctermfg=16  ctermbg=110 cterm=bold gui=bold guifg=#111111 guibg=#7dcfff
highlight StatusLine   cterm=NONE ctermfg=252 ctermbg=238 gui=NONE guifg=#d4d4d4 guibg=#2a2f3a
highlight StatusLineNC cterm=NONE ctermfg=244 ctermbg=236 gui=NONE guifg=#7f8490 guibg=#1f2330

" ================= Key mappings =================
inoremap jk <Esc>

nnoremap L $
vnoremap L $
nnoremap H ^
vnoremap H ^

" Quick indent
nnoremap > >>
nnoremap < <<
vnoremap > >gv
vnoremap < <gv

" 不建议再映射成普通模式里的 wq 序列，容易影响正常输入节奏
nnoremap wq :wq!<CR>

nnoremap dL d$
nnoremap dH d^

" ================= Selection behavior =================
" 保持更接近标准 Vim 的行为
set selection=inclusive
set selectmode=

" ================= Cursor Shape =================
" 你的目标：
" insert  -> blinking beam
" normal  -> blinking block
" replace -> steady block

if has('gui_running')
    " gVim / GUI Vim / 部分 Win32 console
    set guicursor=n-v-c:block-blinkwait700-blinkon400-blinkoff250,\
                \i-ci:ver35-blinkwait700-blinkon400-blinkoff250,\
                \r-cr:block-blinkon0
else
    " Terminal Vim
    let &t_SI = "\<Esc>[5 q"   " Insert: blinking beam
    let &t_SR = "\<Esc>[2 q"   " Replace: steady block
    let &t_EI = "\<Esc>[1 q"   " Normal: blinking block
endif

" 启动后强制回一次普通模式光标，避免继承上一个程序的光标状态
autocmd VimEnter * silent! execute "normal! \<Esc>"

" ================= Files =================
set nobackup
set nowritebackup
set noswapfile

set undofile

if !empty($XDG_CACHE_HOME)
    let s:vimcache = $XDG_CACHE_HOME . '/vim'
else
    let s:vimcache = expand('~/.cache/vim')
endif

call mkdir(s:vimcache . '/undo', 'p')
call mkdir(s:vimcache . '/backup', 'p')
call mkdir(s:vimcache . '/swap', 'p')

execute 'set undodir='   . fnameescape(s:vimcache . '/undo//')
execute 'set backupdir=' . fnameescape(s:vimcache . '/backup//')
execute 'set directory=' . fnameescape(s:vimcache . '/swap//')
execute 'set viminfo+=n' . fnameescape(s:vimcache . '/viminfo')

" ================= GUI-only =================
if has('gui_running')
    set guifont=Courier_New:h10:cANSI
    set guioptions-=T
    set guioptions-=m
endif