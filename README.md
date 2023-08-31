# PLAGS UT

自動評価付きPythonプログラミング課題管理システム PLAGS UT のリポジトリ．

## 概要

[plags-scripts](https://github.com/plags-org/plags-scripts)によって作成された自動評価付き課題を管理するWebアプリケーションであり，フロントエンドサーバ Front と答案の自動評価を行うバックエンド Judge から成る．
課題演習は，Google Colab上で行うことが想定されている．

![PLAGS UTの概観図](docs/plags_overview.drawio.svg)

東京大学での運用を念頭に開発されており，東京大学が契約したGoogle Workspace for Educationのメールアドレス（[ECCSクラウドメール](https://utelecon.adm.u-tokyo.ac.jp/eccs_cloud_email)）を利用したユーザ認証を行う．

## 開発と運用

[東京大学数理・情報教育研究センター](http://www.mi.u-tokyo.ac.jp/)の2020年度～2023年度予算に基づいて，株式会社シャビセンスと[佐藤重幸](https://github.com/satoshigeyuki)によって開発された．
2020年度～2023年度の[「Pythonプログラミング入門」](https://utokyo-ipp.github.io/course)及び[「アルゴリズム入門」](https://lecture.ecc.u-tokyo.ac.jp/johzu/joho-kagaku/)にて運用された．

## 本リポジトリの管理ポリシー

Pull requestは受け付けていない．作成されても機械的にrejectされる．また，デフォルトブランチについてもforce pushで更新されることがある．

本リポジトリへの問い合わせには，issueを利用すること．

## ライセンス

[LICENSE](LICENSE)を参照．
