Rails.application.routes.draw do
  root "home#index"
  # resources :ignored  (a comment, not a route)

  scope :api, defaults: { format: :json } do
    devise_for :users, controllers: { sessions: :sessions },
                       path_names: { sign_in: :login }

    resource :user, only: [:show, :update]

    resources :articles, param: :slug, except: [:edit, :new] do
      resource :favorite, only: [:create, :destroy]
      resources :comments, only: [:index, :destroy]
      get :feed, on: :collection
      member do
        post :publish
      end
    end
  end

  namespace :admin do
    resources :reports, only: :index
    match "export", to: "reports#export", via: [:get, :post]
  end
end
