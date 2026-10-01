package models

import "gorm.io/gorm"

type UserModel struct {
	ID           uint    `gorm:"primaryKey"`
	Email        string  `gorm:"column:email;uniqueIndex"`
	Bio          string  `gorm:"size:1024"`
	Image        *string
	PasswordHash string  `gorm:"column:password;not null"`
}

type ArticleModel struct {
	gorm.Model
	Slug     string `gorm:"uniqueIndex"`
	Title    string
	Author   UserModel
	AuthorID uint
	Tags     []Category `gorm:"many2many:article_categories;"`
}

type Category struct {
	gorm.Model
	Name string
}

func (Category) TableName() string { return "categories" }

// Not a model: no gorm.Model and no gorm tags.
type ArticleResponse struct {
	Title string `json:"title"`
}
