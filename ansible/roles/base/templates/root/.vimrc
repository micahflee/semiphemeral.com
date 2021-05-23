filetype indent plugin on
syntax on
set number
set backspace=indent,eol,start
set autoindent
set tabstop=4
set shiftwidth=4
set softtabstop=4
set expandtab
set incsearch
set history=1000
set wildmenu
set wildmode=list:longest
set synmaxcol=0   " handles syntax highlighting for really long lines
set mouse-=a
set showmatch
highlight ExtraWhitespace ctermbg=red guibg=red
match ExtraWhitespace /\s\+$/
